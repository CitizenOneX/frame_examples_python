import asyncio

from frame_msg import FrameMsg, RxIMU, TxCode

async def main():
    """
    Subscribe to IMU updates from Frame and print them to the console
    """
    frame = FrameMsg()
    try:
        await frame.connect()

        # Let the user know we're starting
        await frame.print_short_text('Loading...')

        # debug only: check our current battery level and memory usage (which varies between 16kb and 31kb or so even after the VM init)
        print(f"Battery Level/Memory used: {await frame.send_lua('print(frame.battery_level() .. " / " .. collectgarbage("count"))', await_print=True)}")

        # send the std lua files to Frame that handle data accumulation, TxCode signalling and IMU sending
        await frame.upload_stdlua_libs(lib_names=['data', 'code', 'imu'])

        # Send the main lua application from this project to Frame that will run the app
        await frame.upload_frame_app(local_filename="lua/imu_frame_app.lua")

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

        # hook up the RxIMU receiver
        rx_imu = RxIMU(smoothing_samples=5)
        imu_queue = await rx_imu.attach(frame)

        # Subscribe for IMU updates
        await frame.send_message(0x40, TxCode(value=1).pack())

        for _ in range(1,100):
            # get the IMU update as soon as it arrives
            imu_update = await asyncio.wait_for(imu_queue.get(), timeout=10.0)
            print(f"{imu_update}")

        # Unsubscribe for IMU updates
        await frame.send_message(0x40, TxCode(value=0).pack())

        # stop the IMU listener and clean up its resources
        rx_imu.detach(frame)

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