import asyncio
from pathlib import Path
from importlib.resources import files

from frame_ble import FrameBle
from frame_msg import TxSprite, TxImageSpriteBlock

async def main():
    """
    Displays a sample image on the Frame display as a progressive sprite, rendered incrementally.
    Because each slice of the image is relatively small, peak memory usage on Frame is smaller than with a single
    large sprite when constituent packets are concatenated.

    The images is a JPEG image, so it is first quantized by TxSprite to 16 colors (that is, 4-bits-per-pixel).
    The image is too large for the display (and memory) so it is resized to fit, preserving aspect ratio.

    This will not be the standard palette from the Frame firmware so the frameside app
    (lua/sprite_frame_app.lua) calls `sprite.set_palette()` before the `frame.display.bitmap()` call.
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

        # send the std lua files to Frame that handle data accumulation and sprite parsing
        for stdlua in ['data', 'image_sprite_block']:
            await frame.upload_file_from_string(files("frame_msg").joinpath(f"lua/{stdlua}.min.lua").read_text(), f"{stdlua}.min.lua")

        # Send the main lua application from this project to Frame that will run the app
        # to display the sprites when the messages arrive
        # We rename the file slightly when we copy it, although it isn't necessary
        await frame.upload_file("lua/prog_sprite_frame_app.lua", "frame_app.lua")

        # attach the print response handler so we can see stdout from Frame Lua print() statements
        # any await_print=True commands will echo the acknowledgement byte (e.g. "1"), so one can assign
        # the handler after the frameside app is running to remove that noise from the log
        frame._user_print_response_handler = print

        # "require" the main lua file to run it
        # Note: we can't await_print here because the require() doesn't return - it has a main loop
        await frame.send_lua("require('frame_app')", await_print=False)

        # give Frame a moment to start the frameside app,
        # based on how much work the app does before it's ready to process incoming data
        await asyncio.sleep(0.1)

        # Now that the Frameside app has started there is no need to send snippets of Lua
        # code directly (in fact, we would need to send a break_signal if we wanted to because
        # the main app loop on Frame is running).
        # From this point we do message-passing with first-class types and send_message() (or send_data())

        # Quantize and send the image to Frame in chunks
        # Note that the frameside app is expecting a message of type TxSprite on msgCode 0x20
        sprite = TxSprite.from_image_bytes(Path("images/koala.jpg").read_bytes(), max_pixels=64000)
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