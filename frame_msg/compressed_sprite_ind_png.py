import asyncio
from pathlib import Path
from importlib.resources import files

from frame_ble import FrameBle
from frame_msg import TxSprite, TxImageSpriteBlock

async def send_compressed_image_sprite_block(frame: FrameBle, image_path: str):
    # TODO add check to sprite constructors, if packed size would be > 4k, throw exception indicating ISB must be used
    sprite = TxSprite.from_indexed_png_bytes(Path(image_path).read_bytes(), compress=True)

    isb = TxImageSpriteBlock(sprite)
    # send the Image Sprite Block header
    await frame.send_message(0x20, isb.pack())
    # then send all the slices
    for spr in isb.sprite_lines:
        await frame.send_message(0x20, spr.pack())

async def main():
    """
    Displays sample images on the Frame display compressed for transmission using lz4 compression

    The images are indexed (palette) PNG images, in 2, 4, and 16 colors (that is, 1-, 2- and 4-bits-per-pixel).

    They are using the standard palette from the Frame firmware. If you want to display sprites that have
    palettes of other colors, the frameside app must call `sprite.set_palette()` (which lua/sprite_frame_app.lua does)
    or call the underlying `frame.display.assign_color()` before the `frame.display.bitmap()` call.
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

        # send the std lua files to Frame that handle data accumulation and sprite parsing
        for stdlua in ['data', 'sprite']:
            await frame.upload_file_from_string(files("frame_msg").joinpath(f"lua/{stdlua}.lua").read_text(), f"{stdlua}.lua")

        # Send the main lua application from this project to Frame that will run the app
        # to display the sprites when the messages arrive
        # We rename the file slightly when we copy it, although it isn't necessary
        #await frame.upload_file("lua/compressed_sprite_frame_app.lua", "frame_app.lua")
        await frame.upload_file("lua/compressed_prog_sprite_frame_app.lua", "frame_app.lua")

        # attach the print response handler so we can see stdout from Frame Lua print() statements
        # any await_print=True commands will echo the acknowledgement byte (e.g. "1"), so one can assign
        # the handler after the frameside app is running to remove that noise from the log
        frame._user_print_response_handler = print

        # "require" the main lua file to run it
        # Note: we can't await_print here because the require() doesn't return - it has a main loop
        await frame.send_lua("require('frame_app')", await_print=False)

        # give Frame a moment to start the frameside app,
        # based on how much work the app does before it's ready to process incoming data
        await asyncio.sleep(2.0)

        # Now that the Frameside app has started there is no need to send snippets of Lua
        # code directly (in fact, we would need to send a break_signal if we wanted to because
        # the main app loop on Frame is running).
        # From this point we do message-passing with first-class types and send_message() (or send_data())

        # send the 1-, 2- and 4-bit images to Frame in compressed slices
        # Note that the frameside app is expecting a message of type TxImageSpriteBlock on msgCode 0x20
        await send_compressed_image_sprite_block(frame, "images/logo_1bit.png")
        await send_compressed_image_sprite_block(frame, "images/street_2bit.png")
        await send_compressed_image_sprite_block(frame, "images/hotdog_4bit.png")

        await asyncio.sleep(5.0)

        # unhook the print handler
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