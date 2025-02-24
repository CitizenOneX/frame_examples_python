import asyncio
import io
from PIL import Image

from frame_msg import FrameMsg, RxAudio, RxPhoto, TxCode, TxCaptureSettings
import time

async def main():
    """
    Subscribe to an Audio stream from Frame and take periodic photos
    """
    frame = FrameMsg()
    speaker = None

    try:
        await frame.connect()

        # Let the user know we're starting
        await frame.print_short_text('Loading...')

        # debug only: check our current battery level and memory usage (which varies between 16kb and 31kb or so even after the VM init)
        batt_mem = await frame.send_lua('print(frame.battery_level() .. " / " .. collectgarbage("count"))', await_print=True)
        print(f"Battery Level/Memory used: {batt_mem}")

        # send the std lua files to Frame that handle data accumulation, TxCode signalling, audio and camera
        await frame.upload_stdlua_libs(lib_names=['data', 'code', 'audio', 'camera'])

        # Send the main lua application from this project to Frame that will run the app
        await frame.upload_frame_app(local_filename="lua/audio_video_frame_app.lua")

        # attach the print response handler so we can see stdout from Frame Lua print() statements
        frame.attach_print_response_handler()

        # "require" the main frame_app lua file to run it, and block until it has started.
        # It signals that it is ready by sending something on the string response channel.
        await frame.start_frame_app()

        # hook up the RxPhoto receiver
        rx_photo = RxPhoto()
        photo_queue = await rx_photo.attach(frame)

        # hook up the RxAudio receiver
        rx_audio = RxAudio(streaming=True)
        audio_queue = await rx_audio.attach(frame)

        # Subscribe for streaming audio
        await frame.send_message(0x30, TxCode(value=1).pack())

        print('Starting streaming: Ctrl-C to cancel')

        # compute the capture msg once
        capture_msg_bytes = TxCaptureSettings(resolution=512, quality_index=0, pan=-40).pack()

        start_time = time.time()

        while True:
            try:
                # get the audio samples as soon as they arrive
                audio_samples = await asyncio.wait_for(audio_queue.get(), timeout=10.0)

                # after streaming is canceled, a None will be put in the queue
                if audio_samples is None:
                    break

                # TODO send/save audio samples

                # Check if it's been 5 seconds since the last photo request
                current_time = time.time()
                if current_time - start_time >= 5:
                    await frame.send_message(0x0d, capture_msg_bytes)
                    start_time = current_time
                    jpeg_bytes = await asyncio.wait_for(photo_queue.get(), timeout=10.0)
                    # TODO send/save photo
                    # for the moment display the image in the system viewer
                    image = Image.open(io.BytesIO(jpeg_bytes))
                    image.show()


            except asyncio.CancelledError:
                print("Received interrupt, shutting down...")
                await frame.send_message(0x30, TxCode(value=0).pack())
                break

            except Exception as e:
                print(f"Error processing audio: {e}")
                break

        # stop the audio stream listener and clean up its resources
        rx_audio.detach(frame)

        # stop the photo listener and clean up its resources
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