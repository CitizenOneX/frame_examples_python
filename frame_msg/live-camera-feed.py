import asyncio
from PIL import Image
import io
import cv2
import numpy as np
import threading
import queue

from frame_msg import FrameMsg, RxPhoto, TxCaptureSettings

class ImageDisplayThread:
    def __init__(self, window_name="Camera Feed"):
        self.window_name = window_name
        self.image_queue = queue.Queue(maxsize=1)
        self.running = True
        self.thread = threading.Thread(target=self.run)
        self.thread.daemon = True
        
    def start(self):
        self.thread.start()
        
    def stop(self):
        self.running = False
        if self.thread.is_alive():
            self.thread.join(timeout=1.0)
        cv2.destroyAllWindows()
        
    def update_image(self, jpeg_bytes):
        try:
            # Replace old image with new one
            if self.image_queue.full():
                try:
                    self.image_queue.get_nowait()
                except queue.Empty:
                    pass
            self.image_queue.put_nowait(jpeg_bytes)
        except queue.Full:
            pass  # Skip frame if queue is full
    
    def run(self):
        cv2.namedWindow(self.window_name, cv2.WINDOW_NORMAL)
        
        while self.running:
            try:
                # Check if there's a new image
                try:
                    jpeg_bytes = self.image_queue.get(timeout=0.1)
                    
                    # Convert PIL Image to OpenCV format
                    pil_image = Image.open(io.BytesIO(jpeg_bytes))
                    cv_image = np.array(pil_image)
                    # Convert RGB to BGR (OpenCV uses BGR)
                    if cv_image.shape[2] == 3:  # If it has 3 channels
                        cv_image = cv2.cvtColor(cv_image, cv2.COLOR_RGB2BGR)
                    
                    # Display image
                    cv2.imshow(self.window_name, cv_image)
                except queue.Empty:
                    pass
                
                # Process events and check for key press
                key = cv2.waitKey(10) & 0xFF
                if key == 27:  # ESC key
                    self.running = False
                    break
                    
            except Exception as e:
                print(f"Error in display thread: {e}")
                break

async def main():
    """
    Take photos continuously using the Frame camera and display them in an OpenCV window
    """
    frame = None
    display_thread = None
    rx_photo = None
    
    try:
        # Initialize display thread
        display_thread = ImageDisplayThread()
        display_thread.start()
        
        frame = FrameMsg()
        await frame.connect()

        # debug only: check our current battery level and memory usage
        batt_mem = await frame.send_lua('print(frame.battery_level() .. " / " .. collectgarbage("count"))', await_print=True)
        print(f"Battery Level/Memory used: {batt_mem}")

        # Let the user know we're starting
        await frame.print_short_text('Loading...')

        # send the std lua files to Frame
        await frame.upload_stdlua_libs(lib_names=['data', 'camera'])

        # Send the main lua application
        await frame.upload_frame_app(local_filename="lua/camera_frame_app.lua")

        frame.attach_print_response_handler()

        # Start the frame app
        await frame.start_frame_app()

        # hook up the RxPhoto receiver
        rx_photo = RxPhoto()
        photo_queue = await rx_photo.attach(frame)

        # give the frame some time for the autoexposure loop to run
        print("Letting autoexposure loop run for 5 seconds to settle")
        await asyncio.sleep(5.0)
        print("Starting continuous capture")

        # Main capture loop
        capture_count = 0
        while True:
            if not display_thread.running:
                print("Display window closed, exiting...")
                break
                
            # Request a photo
            await frame.send_message(0x0d, TxCaptureSettings(resolution=720).pack())
            
            # get the jpeg bytes
            jpeg_bytes = await asyncio.wait_for(photo_queue.get(), timeout=10.0)
            
            # Update the display
            display_thread.update_image(jpeg_bytes)
            
            capture_count += 1
            print(f"Captured frame {capture_count}", end="\r")
            
            # Small delay between captures
            await asyncio.sleep(0.1)  # Adjust this value as needed
            
    except asyncio.CancelledError:
        print("\nCapture loop cancelled")
    except Exception as e:
        print(f"\nAn error occurred: {e}")
    finally:
        # Clean up resources
        print("\nCleaning up resources...")
        if rx_photo and frame:
            rx_photo.detach(frame)
        if frame:
            frame.detach_print_response_handler()
            await frame.stop_frame_app()
            await frame.disconnect()
        if display_thread:
            display_thread.stop()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nProgram interrupted by user")
