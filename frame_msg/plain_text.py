import asyncio
from importlib.resources import files

from frame_ble import FrameBle
from frame_msg import TxPlainText

async def main():
    """
    Print Plain Text on Frame's display using TxPlainText message
    """
    frame = FrameBle()
    try:
        await frame.connect()

        # Send a break signal to Frame in case it has a loop running from another app
        await frame.send_break_signal()

        # Let the user know we're starting
        await frame.send_lua("frame.display.text('Loading...',1,1);frame.display.show();print(1)", await_print=True)

        # debug only: check our current battery level and memory usage (which varies between 16kb and 31kb or so even after the VM init)
        print(f"Battery Level/Memory used: {await frame.send_lua('print(frame.battery_level() .. " / " .. collectgarbage("count"))', await_print=True)}")

        # send the std lua files to Frame that handle data accumulation and text display
        for stdlua in ['data', 'plain_text']:
            await frame.upload_file_from_string(files("frame_msg").joinpath(f"lua/{stdlua}.min.lua").read_text(), f"{stdlua}.min.lua")

        # Send the main lua application from this project to Frame that will run the app
        # to display the text when the messages arrive
        # We rename the file slightly when we copy it, although it isn't necessary
        await frame.upload_file("lua/plain_text_frame_app.lua", "frame_app.lua")

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

        # Send the text for display on Frame
        # Note that the frameside app is expecting a message of type TxPlainText on msgCode 0x0a
        for display_string in ["red", "orange", "yellow", "red\norange\nyellow", " "]:
            await frame.send_message(0x0a, TxPlainText(display_string).pack())
            await asyncio.sleep(1.0)

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