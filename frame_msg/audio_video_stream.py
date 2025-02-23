import asyncio
import struct

from frame_msg import FrameMsg, RxAudio, TxCode

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

        # hook up the RxAudio receiver
        rx_audio = RxAudio(streaming=True)
        audio_queue = await rx_audio.attach(frame)

        # Subscribe for streaming audio
        await frame.send_message(0x30, TxCode(value=1).pack())

        print('Starting streaming: Ctrl-C to cancel')

        while True:
            try:
                # get the audio samples as soon as they arrive
                audio_samples = await asyncio.wait_for(audio_queue.get(), timeout=10.0)

                # after streaming is canceled, a None will be put in the queue
                if audio_samples is None:
                    break

                # TODO send/save audio samples
                # TODO periodically request a photo

            except asyncio.CancelledError:
                print("Received interrupt, shutting down...")
                await frame.send_message(0x30, TxCode(value=0).pack())
                break

            except Exception as e:
                print(f"Error processing audio: {e}")
                break

        # stop the audio stream listener and clean up its resources
        rx_audio.detach(frame)

        # unhook the print handler
        frame.detach_print_response_handler()

        # break out of the frame app loop and reboot Frame
        await frame.stop_frame_app(reset=True)

    except Exception as e:
        print(f"An error occurred: {e}")
    finally:
        # clean disconnection
        await frame.disconnect()

if __name__ == "__main__":
    asyncio.run(main())