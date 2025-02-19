import asyncio
from importlib.resources import files
from PIL import Image
import io
import numpy as np
import keyboard

from frame_ble import FrameBle
from frame_msg import RxPhoto, TxCaptureSettings, TxSprite, TxImageSpriteBlock

async def main():
    """
    Repeatedly take photos using the Frame camera and display them on the Frame display
    """
    frame = FrameBle()
    try:
        await frame.connect()

        # Send a break signal to Frame in case it currently has an application loop running
        await frame.send_break_signal()

        # Send a reset signal to Frame to restart the Lua VM, initialize memory to a known state
        await frame.send_reset_signal()

        # Send a break signal to Frame in case it automatically starts a saved main.lua
        await frame.send_break_signal()

        # Let the user know we're starting
        await frame.send_lua("frame.display.text('Loading...',1,1);frame.display.show();print(1)", await_print=True)

        # debug only: check our current battery level and memory usage (which varies between 16kb and 31kb or so even after the VM init)
        print(f"Battery Level/Memory used: {await frame.send_lua('print(frame.battery_level() .. " / " .. collectgarbage("count"))', await_print=True)}")

        # send the std lua files to Frame that handle data accumulation and camera
        for stdlua in ['data', 'camera', 'image_sprite_block']:
            await frame.upload_file_from_string(files("frame_msg").joinpath(f"lua/{stdlua}.min.lua").read_text(), f"{stdlua}.min.lua")

        # Send the main lua application from this project to Frame that will run the app
        # to display the text when the messages arrive
        # We rename the file slightly when we copy it, although it isn't necessary
        await frame.upload_file("lua/camera_image_sprite_block_frame_app.lua", "frame_app.lua")

        # attach the print response handler so we can see stdout from Frame Lua print() statements
        # If we assigned this handler before the frameside app was running,
        # any await_print=True commands will echo the acknowledgement byte (e.g. "1"), but if we assign
        # the handler now we'll see any lua exceptions (or stdout print statements)
        frame._user_print_response_handler = print

        # "require" the main lua file to run it
        # Note: we can't await_print here because the require() doesn't return - it has a main loop
        await frame.send_lua("require('frame_app')", await_print=False)

        # give Frame a moment to start the frameside app,
        # based on how much work the app does before it's ready to process incoming data
        await asyncio.sleep(0.5)

        # Now that the Frameside app has started there is no need to send snippets of Lua
        # code directly (in fact, we would need to send a break_signal if we wanted to because
        # the main app loop on Frame is running).
        # From this point we do message-passing with first-class types and send_message() (or send_data())

        # create an object made for receiving photos from Frame
        rx_photo = RxPhoto()
        await rx_photo.start()

        # hook up the RxPhoto receiver
        frame._user_data_response_handler = rx_photo.handle_data

        # compute the capture msg once
        capture_msg_bytes = TxCaptureSettings(resolution=256, quality_index=0).pack()

        key_pressed = False

        # key press handler for stopping the loop
        def on_key_press(event):
            nonlocal key_pressed
            key_pressed = True

        keyboard.hook(on_key_press)  # Listen for key presses

        print("Camera capture/display loop starting: Press 'q' to quit")

        while not key_pressed:

            # Request the photo capture
            await frame.send_message(0x0d, capture_msg_bytes)

            # get the jpeg bytes as soon as they're ready
            jpeg_bytes = await asyncio.wait_for(rx_photo.queue.get(), timeout=10.0)

            # load the image with PIL
            image = Image.open(io.BytesIO(jpeg_bytes))
            # '1': black and white with dither
            image = image.convert('1')

            # regrettably need to unpack the nicely packed bits into bytes
            data_array = np.frombuffer(image.tobytes(), dtype=np.uint8)
            unpacked = np.unpackbits(data_array)

            # extract pixel data from unpacked.tobytes() at 1bpp and create TxSprite manually
            sprite = TxSprite(width=256,
                            height=256,
                            num_colors=2,
                            palette_data=bytes([0,0,0,255,255,255]),
                            pixel_data=unpacked.tobytes())

            # Quantize and send the image to Frame in chunks as an ImageSpriteBlock rendered progressively
            # Note that the frameside app is expecting a message of type TxImageSpriteBlock on msgCode 0x20
            isb = TxImageSpriteBlock(sprite, sprite_line_height=32)

            # send the Image Sprite Block header
            await frame.send_message(0x20, isb.pack())

            # then send all the slices
            for spr in isb.sprite_lines:
                await frame.send_message(0x20, spr.pack())


        # stop the photo handler and clean up resources
        rx_photo.stop()

        # detach the rx data handler
        frame._user_data_response_handler = None

        # unhook the print logger
        frame._user_print_response_handler = None

        # stop the app loop
        await frame.send_break_signal()

        # reinitialize the Lua VM to clear the memory state
        await frame.send_reset_signal()

    except Exception as e:
        print(f"An error occurred: {e}")
    finally:
        # clean disconnection
        if frame.is_connected():
            await frame.disconnect()

if __name__ == "__main__":
    asyncio.run(main())