import asyncio
from importlib.resources import files
from PIL import Image
import io

from frame_ble import FrameBle
from frame_msg import RxTap, TxCode

async def main():
    """
    Register multi-taps from Frame and print them to the console
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

        # send the std lua files to Frame that handle data accumulation, TxCode signalling and Tap sending
        for stdlua in ['data', 'code', 'tap']:
            await frame.upload_file_from_string(files("frame_msg").joinpath(f"lua/{stdlua}.min.lua").read_text(), f"{stdlua}.min.lua")

        # Send the main lua application from this project to Frame that will run the app
        # We rename the file slightly when we copy it, although it isn't necessary
        await frame.upload_file("lua/tap_frame_app.lua", "frame_app.lua")

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
        await asyncio.sleep(0.2)

        # Now that the Frameside app has started there is no need to send snippets of Lua
        # code directly (in fact, we would need to send a break_signal if we wanted to because
        # the main app loop on Frame is running).
        # From this point we do message-passing with first-class types and send_message() (or send_data())

        rx_tap = RxTap()
        await rx_tap.start()

        # hook up the RxPhoto receiver
        frame._user_data_response_handler = rx_tap.handle_data

        # Subscribe for Taps
        await frame.send_message(0x10, TxCode(value=1).pack())

        for _ in range(1,10):
            # get the multi-tap count as soon as it arrives
            tap_count = await asyncio.wait_for(rx_tap.queue.get(), timeout=10.0)
            print(f"{tap_count}-tap received")

        # Unsubscribe for Taps
        await frame.send_message(0x10, TxCode(value=0).pack())

        # stop the tap listener and clean up resources
        rx_tap.stop()

        # unhook the print handler
        frame._user_print_response_handler = None

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