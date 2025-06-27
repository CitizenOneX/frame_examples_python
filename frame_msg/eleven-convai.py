import asyncio

from frame_msg import FrameMsg, RxAudio, TxCode
from pvspeaker import PvSpeaker

import os
import signal
import sys
from elevenlabs.client import ElevenLabs
from elevenlabs.conversational_ai.conversation import Conversation, AudioInterface
from typing import Callable
import threading
import queue
import numpy as np

class FrameAudioInterface(AudioInterface):
    """Custom AudioInterface implementation for Frame device."""
    
    def __init__(self, frame: FrameMsg):
        self.frame = frame
        self.input_callback = None
        self.speaker = None
        self.frame_audio_queue = None  # asyncio queue from Frame
        self.thread_audio_queue = queue.Queue()  # thread-safe queue for bridging
        self.rx_audio = None
        self.should_stop = threading.Event()
        self.input_thread = None
        self.output_thread = None
        self.bridge_task = None
        self.output_queue = queue.Queue()
        self.setup_complete = threading.Event()
    
    async def setup_frame_audio(self):
        """Set up Frame's audio streaming - must be called in main async context."""
        try:
            # Set up audio input from Frame
            self.rx_audio = RxAudio(streaming=True)
            
            # Attach the RxAudio receiver
            self.frame_audio_queue = await self.rx_audio.attach(self.frame)
            
            # Subscribe for streaming audio from Frame
            await self.frame.send_message(0x30, TxCode(value=1).pack())
            
            # Start the bridge task to move audio from asyncio queue to thread queue
            self.bridge_task = asyncio.create_task(self._bridge_audio_queues())
            
            # Signal that setup is complete
            self.setup_complete.set()
            print("Frame audio setup complete")
        except Exception as e:
            print(f"Error setting up Frame audio: {e}")
            import traceback
            traceback.print_exc()
            raise
    
    async def _bridge_audio_queues(self):
        """Bridge between asyncio queue and thread-safe queue."""
        try:
            while not self.should_stop.is_set():
                try:
                    # Get audio from Frame's asyncio queue with timeout
                    audio_samples = await asyncio.wait_for(
                        self.frame_audio_queue.get(), 
                        timeout=0.1
                    )
                    
                    if audio_samples is None:
                        break
                    
                    # Put into thread-safe queue
                    try:
                        self.thread_audio_queue.put_nowait(audio_samples)
                    except queue.Full:
                        # Drop audio if queue is full
                        print("Thread audio queue full, dropping audio")
                        
                except asyncio.TimeoutError:
                    # No audio available, continue
                    continue
                except Exception as e:
                    print(f"Error in audio bridge: {e}")
                    break
        except Exception as e:
            print(f"Audio bridge task error: {e}")
        finally:
            # Signal end of audio stream
            self.thread_audio_queue.put(None)
    
    def _upsample_audio(self, audio_8khz, target_rate=16000, source_rate=8000):
        """Upsample audio from 8kHz to 16kHz using simple interpolation."""
        ratio = target_rate // source_rate
        upsampled = np.repeat(audio_8khz, ratio)
        return upsampled
    
    def _downsample_audio(self, audio_16khz, target_rate=8000, source_rate=16000):
        """Downsample audio from 16kHz to 8kHz by taking every other sample."""
        ratio = source_rate // target_rate
        downsampled = audio_16khz[::ratio]
        return downsampled
    
    def start(self, input_callback: Callable[[bytes], None]):
        """Start the audio interface for Frame."""
        print("Starting Frame audio interface...")
        self.input_callback = input_callback
        
        # Set up audio output player - Frame expects 8kHz, 8-bit
        self.speaker = PvSpeaker(
            sample_rate=8000,   # Frame operates at 8kHz
            bits_per_sample=8,  # Frame expects 8-bit
            buffer_size_secs=5,
            device_index=-1
        )
        self.speaker.start()
        print("PvSpeaker started (8kHz, 8-bit)")
        
        # Start threads
        self.should_stop.clear()
        self.input_thread = threading.Thread(target=self._input_thread, daemon=True)
        self.output_thread = threading.Thread(target=self._output_thread, daemon=True)
        self.input_thread.start()
        self.output_thread.start()
        print("Audio threads started")
    
    def stop(self):
        """Stop the audio interface."""
        print("Stopping Frame audio interface...")
        self.should_stop.set()
        
        # Cancel the bridge task
        if self.bridge_task:
            self.bridge_task.cancel()
        
        if self.input_thread and self.input_thread.is_alive():
            self.input_thread.join(timeout=2)
        if self.output_thread and self.output_thread.is_alive():
            self.output_thread.join(timeout=2)
            
        if self.speaker:
            try:
                self.speaker.flush()
                self.speaker.stop()
                self.speaker.delete()
            except Exception as e:
                print(f"Error stopping speaker: {e}")
    
    def output(self, audio: bytes):
        """Output audio to Frame's speaker."""
        try:
            self.output_queue.put(audio, block=False)
        except queue.Full:
            # Drop audio if queue is full to prevent blocking
            print("Audio output queue full, dropping audio")
    
    def interrupt(self):
        """Clear the audio output queue to stop current playback."""
        try:
            while True:
                self.output_queue.get(block=False)
        except queue.Empty:
            pass
    
    def _input_thread(self):
        """Thread to handle audio input from Frame."""
        print("Input thread started, waiting for setup...")
        # Wait for setup to complete
        if not self.setup_complete.wait(timeout=10):
            print("Timeout waiting for Frame audio setup")
            return
            
        print("Input thread running...")
        
        while not self.should_stop.is_set():
            try:
                # Get audio samples from thread-safe queue
                try:
                    audio_samples = self.thread_audio_queue.get(timeout=0.25)
                except queue.Empty:
                    continue
                
                if audio_samples is None:
                    print("Received None from audio queue, stopping")
                    break
                
                if len(audio_samples) == 0:
                    continue
                
                # Convert Frame's 8-bit audio to 16-bit for ElevenLabs
                try:
                    # Convert bytes to numpy array of signed 8-bit integers
                    audio_8bit = np.frombuffer(audio_samples, dtype=np.int8)
                    
                    # Convert to 16-bit (signed)
                    audio_16bit = audio_8bit.astype(np.int16) * 256
                    
                    # Upsample from 8kHz to 16kHz
                    audio_16khz = self._upsample_audio(audio_16bit)
                    
                    # Convert back to bytes
                    pcm_16bit = audio_16khz.astype(np.int16).tobytes()
                    
                    # Send to ElevenLabs
                    if self.input_callback:
                        self.input_callback(pcm_16bit)
                        
                except Exception as e:
                    print(f"Error converting audio: {e}")
                    continue
                    
            except Exception as e:
                print(f"Error in input loop: {e}")
                import traceback
                traceback.print_exc()
                break
        
        print("Input thread stopped")
    
    def _output_thread(self):
        """Thread to handle audio output to Frame's speaker."""
        print("Output thread started...")
        
        while not self.should_stop.is_set():
            try:
                # Get audio from ElevenLabs (16-bit PCM at 16kHz)
                audio_16bit = self.output_queue.get(timeout=0.25)
                
                try:
                    # Convert from 16-bit PCM to numpy array
                    audio_16khz = np.frombuffer(audio_16bit, dtype=np.int16)
                    
                    # Downsample from 16kHz to 8kHz
                    audio_8khz = self._downsample_audio(audio_16khz)
                    
                    # Convert from 16-bit to 8-bit unsigned (0-255 range for PvSpeaker)
                    audio_8bit_signed = (audio_8khz / 256).astype(np.int8)
                    audio_8bit_unsigned = (audio_8bit_signed.astype(np.int16) + 128).astype(np.uint8)
                    
                    # Convert to bytes
                    audio_8bit_bytes = audio_8bit_unsigned.tobytes()
                    
                    # Write to speaker
                    self.speaker.write(audio_8bit_bytes)
                    
                except Exception as e:
                    print(f"Error writing to speaker: {e}")
                
            except queue.Empty:
                continue
            except Exception as e:
                print(f"Error in output thread: {e}")
                break
        
        print("Output thread stopped")

# Global variable to handle shutdown
shutdown_event = threading.Event()

async def main():
    """
    Use Frame with ElevenLabs Conversational AI
    """
    frame = FrameMsg()
    frame_audio = None
    conversation = None

    agent_id = "agent_01jynq02rjevdv9nr3zrqxa4mw"
    api_key = os.getenv("ELEVENLABS_API_KEY")
    
    elevenlabs = ElevenLabs(api_key=api_key)
    
    # Create Frame audio interface
    frame_audio = FrameAudioInterface(frame)
    
    conversation = Conversation(
        # API client and agent ID
        elevenlabs,
        agent_id,

        # Assume auth is required when API_KEY is set
        requires_auth=bool(api_key),

        # Use Frame audio interface
        audio_interface=frame_audio,

        # Simple callbacks that print the conversation to the console
        callback_agent_response=lambda response: print(f"Agent: {response}"),
        callback_agent_response_correction=lambda original, corrected: print(f"Agent: {original} -> {corrected}"),
        callback_user_transcript=lambda transcript: print(f"User: {transcript}"),

        # Uncomment if you want to see latency measurements
        # callback_latency_measurement=lambda latency: print(f"Latency: {latency}ms"),
    )

    try:
        await frame.connect()
        print("Connected to Frame")

        # Initial setup display - only before Frame app starts
        print("Loading Frame app...")
        try:
            await frame.print_short_text('Loading...')
        except Exception as e:
            print(f"Warning: Could not display loading message: {e}")

        # Debug: check battery level and memory usage
        try:
            batt_mem = await frame.send_lua('print(frame.battery_level() .. " / " .. collectgarbage("count"))', await_print=True)
            print(f"Battery Level/Memory used: {batt_mem}")
        except Exception as e:
            print(f"Could not get battery info: {e}")

        # Send the std lua files to Frame
        await frame.upload_stdlua_libs(lib_names=['data', 'code', 'audio'])

        # Send the main lua application
        await frame.upload_frame_app(local_filename="lua/audio_frame_app.lua")

        # Attach print response handler
        frame.attach_print_response_handler()

        # Start the frame app
        await frame.start_frame_app()

        # Set up Frame audio after app is running
        print("Setting up Frame audio...")
        await frame_audio.setup_frame_audio()
        
        print("Starting conversation with ElevenLabs agent...")
        
        # Start the conversation
        conversation.start_session()

        print("Conversation started. Speak to interact with the agent.")
        print("Press Ctrl-C to stop...")

        # Wait for shutdown signal or conversation end
        while not shutdown_event.is_set():
            try:
                await asyncio.sleep(0.1)
            except KeyboardInterrupt:
                break

    except KeyboardInterrupt:
        print("\nInterrupted by user")
    except Exception as e:
        print(f"An error occurred: {e}")
        import traceback
        traceback.print_exc()
    finally:
        print("Cleaning up...")
        
        # Stop conversation
        if conversation:
            try:
                conversation.end_session()
            except Exception as e:
                print(f"Error ending conversation: {e}")
        
        # Stop Frame audio
        if frame_audio:
            try:
                frame_audio.stop()
            except Exception as e:
                print(f"Error stopping Frame audio: {e}")
        
        # Stop Frame audio streaming
        try:
            await frame.send_message(0x30, TxCode(value=0).pack())
        except Exception as e:
            print(f"Error stopping Frame audio streaming: {e}")
        
        # Detach RxAudio
        if frame_audio and frame_audio.rx_audio:
            try:
                frame_audio.rx_audio.detach(frame)
            except Exception as e:
                print(f"Error detaching RxAudio: {e}")
        
        # Clean Frame disconnection
        try:
            frame.detach_print_response_handler()
            await frame.stop_frame_app()
            await frame.disconnect()
        except Exception as e:
            print(f"Error during Frame cleanup: {e}")
        
        print("Cleanup complete")

def signal_handler(sig, frame_obj):
    """Handle Ctrl-C gracefully"""
    print("\nShutdown requested...")
    shutdown_event.set()

if __name__ == "__main__":
    # Set up signal handler
    signal.signal(signal.SIGINT, signal_handler)
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Exiting...")
    
    sys.exit(0)