import asyncio
from PIL import Image
import io

from frame_msg import FrameMsg, RxPhoto, TxManualExpSettings, TxCaptureSettings

async def main():
    """
    Set camera exposure settings manually and take a single photo
    """
    frame = FrameMsg()
    try:
        await frame.connect()

        # debug only: check our current battery level and memory usage (which varies between 16kb and 31kb or so even after the VM init)
        batt_mem = await frame.send_lua('print(frame.battery_level() .. " / " .. collectgarbage("count"))', await_print=True)
        print(f"Battery Level/Memory used: {batt_mem}")

        # Let the user know we're starting
        await frame.print_short_text('Loading...')

        # send the std lua files to Frame that our app needs to handle data accumulation and camera
        await frame.upload_stdlua_libs(lib_names=['data', 'camera', 'code'], minified=False)

        # Send the main lua application from this project to Frame that will run the app
        # to take a photo and send it back when the TxCaptureSettings messages arrive
        await frame.upload_frame_app(local_filename="lua/manualexp_frame_app.lua")

        # attach the print response handler so we can see stdout from Frame Lua print() statements
        # If we assigned this handler before the frameside app was running,
        # any await_print=True commands will echo the acknowledgement byte (e.g. "0" or "1"), but if we assign
        # the handler now we'll see any lua exceptions (or stdout print statements) when the app runs
        frame.attach_print_response_handler()

        # "require" the main frame_app lua file to run it, and block until it has started.
        # It signals that it is ready by sending something on the string response channel.
        await frame.start_frame_app()

        # NOTE: Now that the Frameside app has started there is no need to send snippets of Lua
        # code directly (in fact, we would need to send a break_signal if we wanted to because
        # the main app loop on Frame is running).
        # From this point we do message-passing with first-class types and send_message() (or send_data())

        # hook up the RxPhoto receiver
        rx_photo = RxPhoto()
        photo_queue = await rx_photo.attach(frame)

        # take the default manual exposure settings
        tx_manual_exp = TxManualExpSettings(manual_shutter=10000)

        # send the manual exposure settings to Frame before taking the photo
        await frame.send_message(0x0c, tx_manual_exp.pack())

        # NOTE: it takes up to 200ms for manual camera settings to take effect!
        await asyncio.sleep(0.2)

        # Request the photo by sending a TxCaptureSettings message
        await frame.send_message(0x0d, TxCaptureSettings(resolution=720).pack())

        # get the jpeg bytes as soon as they're ready
        jpeg_bytes = await asyncio.wait_for(photo_queue.get(), timeout=10.0)

        # display the image in the system viewer
        image = Image.open(io.BytesIO(jpeg_bytes))
        image.show()

        # stop the photo receiver and clean up its resources
        rx_photo.detach(frame)

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