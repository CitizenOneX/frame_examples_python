import asyncio
import struct

from frame_msg import FrameMsg, RxAudio, TxCode
from pvspeaker import PvSpeaker

async def main():
    """
    Subscribe to an Audio stream from Frame and play to the default output device using pvspeaker
    """
    frame = FrameMsg()
    speaker = None
    stop_requested = False

    async def stop_audio():
        nonlocal stop_requested
        if not stop_requested:
            print("\nStopping audio...")
            await frame.send_message(0x30, TxCode(value=0).pack())
            stop_requested = True

    try:
        await frame.connect()

        # Let the user know we're starting
        await frame.print_short_text('Loading...')

        # debug only: check our current battery level and memory usage (which varies between 16kb and 31kb or so even after the VM init)
        batt_mem = await frame.send_lua('print(frame.battery_level() .. " / " .. collectgarbage("count"))', await_print=True)
        print(f"Battery Level/Memory used: {batt_mem}")

        # send the std lua files to Frame that handle data accumulation, TxCode signalling and audio
        await frame.upload_stdlua_libs(lib_names=['data', 'code', 'audio'])

        # Send the main lua application from this project to Frame that will run the app
        await frame.upload_frame_app(local_filename="lua/audio_frame_app.lua")

        # attach the print response handler so we can see stdout from Frame Lua print() statements
        frame.attach_print_response_handler()

        # "require" the main frame_app lua file to run it, and block until it has started.
        # It signals that it is ready by sending something on the string response channel.
        await frame.start_frame_app()

        # set up and start the audio output player
        speaker = PvSpeaker(
            sample_rate=8000,
            bits_per_sample=16,
            buffer_size_secs=5,
            device_index=-1)

        speaker.start()

        # hook up the RxAudio receiver in streaming mode rather than whole clip mode
        rx_audio = RxAudio(streaming=True)
        audio_queue = await rx_audio.attach(frame)

        # Subscribe for streaming audio
        await frame.send_message(0x30, TxCode(value=1).pack())

        print("Press Ctrl-C to stop audio...")

        while True:
            try:
                # Try to get audio samples without blocking
                audio_samples = audio_queue.get_nowait()

                # after streaming is canceled, a None will be put in the queue
                if audio_samples is None:
                    break

                # Convert bytes to list of int16 values for PvSpeaker
                # Unpack every 2 bytes as a signed 16-bit integer
                int16_samples = list(struct.unpack(f'<{len(audio_samples)//2}h', audio_samples))

                samples_remaining = int16_samples
                while len(samples_remaining) > 0:
                    bytes_written = speaker.write(samples_remaining)
                    if bytes_written == 0: # buffer is full
                        try:
                            await asyncio.sleep(0.001) # short sleep to prevent CPU spinning
                        except KeyboardInterrupt:
                            await stop_audio()
                            continue
                        continue
                    samples_remaining = samples_remaining[bytes_written:]
            except asyncio.QueueEmpty:
                # No samples available, yield control to other tasks
                try:
                    await asyncio.sleep(0.001)
                except asyncio.exceptions.CancelledError:
                    # ctrl-c came while in the sleep
                    await stop_audio()
                continue
            except KeyboardInterrupt:
                # ctrl-c came at another time
                await stop_audio()
                continue

        # stop the audio stream listener and clean up its resources
        rx_audio.detach(frame)

        # stop the audio output player
        speaker.flush()
        speaker.stop()

        # unhook the print handler
        frame.detach_print_response_handler()

        # break out of the frame app loop and reboot Frame
        await frame.stop_frame_app()

    except Exception as e:
        print(f"An error occurred: {e}")
    finally:
        # clean disconnection
        await frame.disconnect()
        if speaker is not None:
            speaker.delete()

if __name__ == "__main__":
    asyncio.run(main())