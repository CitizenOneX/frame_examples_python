import asyncio
from pathlib import Path

from frame_msg import FrameMsg, TxSprite, TxImageSpriteBlock

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
    frame = FrameMsg()
    try:
        await frame.connect()

        # debug only: check our current battery level and memory usage (which varies between 16kb and 31kb or so even after the VM init)
        print(f"Battery Level/Memory used: {await frame.send_lua('print(frame.battery_level() .. " / " .. collectgarbage("count"))', await_print=True)}")

        # Let the user know we're starting
        await frame.print_short_text('Loading...')

        # send the std lua files to Frame that handle data accumulation and sprite parsing
        await frame.upload_stdlua_libs(lib_names=['data', 'image_sprite_block'])

        # Send the main lua application from this project to Frame that will run the app
        await frame.upload_frame_app(local_filename="lua/prog_sprite_frame_app.lua")

        # attach the print response handler so we can see stdout from Frame Lua print() statements
        # If we assigned this handler before the frameside app was running,
        # any await_print=True commands will echo the acknowledgement byte (e.g. "1"), but if we assign
        # the handler now we'll see any lua exceptions (or stdout print statements)
        frame.attach_print_response_handler()

        # "require" the main frame_app lua file to run it, and block until it has started.
        # It signals that it is ready by sending something on the string response channel.
        await frame.start_frame_app()

        # NOTE: Now that the Frameside app has started there is no need to send snippets of Lua
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

        # unhook the print handler
        frame.detach_print_response_handler()

        # break out of the frame app loop and reboot Frame
        await frame.stop_frame_app()

    except Exception as e:
        print(f"An error occurred: {e}")
    finally:
        # clean disconnection
        await frame.disconnect()

if __name__ == "__main__":
    asyncio.run(main())