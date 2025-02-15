import asyncio
from importlib.resources import files
from PIL import Image
import io

from frame_ble import FrameBle
from frame_msg import RxPhoto, TxCaptureSettings, TxSprite, TxImageSpriteBlock

async def main():
    """
    Take a photo using the Frame camera and display it on the Frame display
    """
    frame = FrameBle()
    try:
        await frame.connect()

        # Send a break signal to Frame in case it has a loop running from another app
        await frame.send_break_signal()

        # Let the user know we're starting
        await frame.send_lua("frame.display.text('Loading...',1,1);frame.display.show();print(1)", await_print=True)

        # debug only: check our current battery level
        print(f"Battery Level: {await frame.send_lua('print(frame.battery_level())', await_print=True)}")

        # send the std lua files to Frame that handle data accumulation and camera
        for stdlua in ['data', 'camera', 'image_sprite_block']:
            await frame.upload_file_from_string(files("frame_msg").joinpath(f"lua/{stdlua}.min.lua").read_text(), f"{stdlua}.min.lua")

        # Send the main lua application from this project to Frame that will run the app
        # to display the text when the messages arrive
        # We rename the file slightly when we copy it, although it isn't necessary
        await frame.upload_file("lua/camera_sprite_frame_app.lua", "frame_app.lua")

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

        rx_photo = RxPhoto()
        await rx_photo.start()

        # hook up the RxPhoto receiver
        frame._user_data_response_handler = rx_photo.handle_data

        # give the frame some time for the autoexposure loop to run (50 times; every 0.1s)
        await asyncio.sleep(5.0)

        # Request the photo capture
        capture_settings = TxCaptureSettings(resolution=720)
        await frame.send_message(0x0d, capture_settings.pack())

        # get the jpeg bytes as soon as they're ready
        jpeg_bytes = await asyncio.wait_for(rx_photo.queue.get(), timeout=10.0)

        # stop the photo handler and clean up resources
        rx_photo.stop()
        frame._user_data_response_handler = None

        # Quantize and send the image to Frame in chunks as an ImageSpriteBlock rendered progressively
        # Note that the frameside app is expecting a message of type TxImageSpriteBlock on msgCode 0x20
        sprite = TxSprite.from_image_bytes(jpeg_bytes, max_pixels=64000)
        isb = TxImageSpriteBlock(sprite, sprite_line_height=20)
        # send the Image Sprite Block header
        await frame.send_message(0x20, isb.pack())
        # then send all the slices
        for spr in isb.sprite_lines:
            await frame.send_message(0x20, spr.pack())

        await asyncio.sleep(5.0)

        # stop the app loop
        await frame.send_break_signal()

    except Exception as e:
        print(f"An error occurred: {e}")
    finally:
        # clean disconnection
        if frame.is_connected():
            await frame.disconnect()

if __name__ == "__main__":
    asyncio.run(main())