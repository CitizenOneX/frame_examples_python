import asyncio
import io
from PIL import Image
from pvspeaker import PvSpeaker

from frame_msg import FrameMsg, RxAudio, RxPhoto, TxCode, TxCaptureSettings
import time

async def main():
    """
    Subscribe to an Audio stream from Frame and play to the default output device using pvspeaker, and take periodic photos
    """
    frame = FrameMsg()
    speaker = None
    stop_requested = False

    async def stop_streaming():
        nonlocal stop_requested
        if not stop_requested:
            print("\nStopping streaming...")
            await frame.send_message(0x30, TxCode(value=0).pack())
            stop_requested = True

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

        # set up and start the audio output player
        speaker = PvSpeaker(
            sample_rate=8000,
            bits_per_sample=8,
            buffer_size_secs=5,
            device_index=-1)

        speaker.start()

        # Subscribe for streaming audio
        await frame.send_message(0x30, TxCode(value=1).pack())

        print('Starting streaming: Ctrl-C to cancel')

        # compute the capture msg once
        capture_msg_bytes = TxCaptureSettings(resolution=512, quality_index=0, pan=-40).pack()

        start_time = time.time()

        while True:
            try:
                # Try to get audio samples without blocking
                audio_samples = audio_queue.get_nowait()

                # after streaming is canceled, a None will be put in the queue
                if audio_samples is None:
                    break

                # since bits_per_sample == 8:
                # reinterpret the bytes as signed 8-bit integers then shift to the uint8 range 0-255
                pcm_data = bytearray(audio_samples)
                for i in range(len(pcm_data)):
                    # Convert signed 8-bit (-128 to 127) to unsigned 8-bit (0 to 255)
                    pcm_data[i] = (pcm_data[i] if pcm_data[i] < 128 else pcm_data[i] - 256) + 128

                # Pass the audio samples to PvSpeaker
                samples_remaining = pcm_data
                while len(samples_remaining) > 0:
                    bytes_written = speaker.write(samples_remaining)
                    if bytes_written == 0: # buffer is full
                        try:
                            await asyncio.sleep(0.001) # short sleep to prevent CPU spinning
                        except KeyboardInterrupt:
                            await stop_streaming()
                            continue
                        continue
                    samples_remaining = samples_remaining[bytes_written:]

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


            except asyncio.QueueEmpty:
                # No samples available, yield control to other tasks
                try:
                    await asyncio.sleep(0.001)
                except asyncio.exceptions.CancelledError:
                    # ctrl-c came while in the sleep
                    await stop_streaming()
                continue
            except KeyboardInterrupt:
                # ctrl-c came at another time
                await stop_streaming()
                continue
            except Exception as e:
                print(f"Error processing stream: {e}")
                break

        # stop the audio output player
        speaker.flush()
        speaker.stop()

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