import asyncio
from PIL import Image
import io

from frame_msg import FrameMsg, RxPhoto, RxMeteringData, TxCode, TxManualExpSettings, TxCaptureSettings

def camera_auto_exposure_algo(
    # Metering data (6 uint8 values: spot_r/g/b, matrix_r/g/b)
    metering_data,
    # Last state of exposure/white balance parameters
    last_state,

    # Default auto exposure settings
    metering="AVERAGE",
    target_exposure=0.18,
    exposure_speed=0.50,
    shutter_limit=8192.0,
    analog_gain_limit=16.0,
    rgb_gain_limit=141.0,

    # Default white balance settings
    white_balance_speed=0.5,
    brightness_constant=4166400.0,
    white_balance_min_activation=50,
    white_balance_max_activation=200,

):
    """
    Auto-adjusts camera exposure and white balance based on scene metrics.

    Args:
        metering_data: 6 uint8 values: spot_r/g/b, matrix_r/g/b
        metering: Metering mode ("SPOT", "CENTER_WEIGHTED", or "AVERAGE")
        target_exposure: Target exposure level (0.0 to 1.0)
        exposure_speed: Speed of exposure adjustment (0.0 to 1.0)
        shutter_limit: Maximum shutter duration (4.0 to 16383.0)
        analog_gain_limit: Maximum analog gain (1.0 to 248.0)
        rgb_gain_limit: Maximum per-channel RGB gain (0.0 to 1023.0)
        white_balance_speed: Speed of white balance adjustment (0.0 to 1.0)
        brightness_constant: Constant for brightness calculation
        white_balance_min_activation: Minimum brightness for white balance
        white_balance_max_activation: Maximum brightness for white balance
        last_state: Previous state of the camera settings

    Returns:
        dict: Updated camera settings and metering information
    """
    # Validate inputs
    if metering not in ["SPOT", "CENTER_WEIGHTED", "AVERAGE"]:
        raise ValueError("metering must be SPOT, CENTER_WEIGHTED or AVERAGE")

    if not (0.0 <= target_exposure <= 1.0):
        raise ValueError("exposure must be between 0 and 1")

    if not (0.0 <= exposure_speed <= 1.0):
        raise ValueError("exposure_speed must be between 0 and 1")

    if not (4.0 <= shutter_limit <= 16383.0):
        raise ValueError("shutter_limit must be between 4 and 16383")

    if not (1.0 <= analog_gain_limit <= 248.0):
        raise ValueError("analog_gain_limit must be between 1 and 248")

    if not (0.0 <= rgb_gain_limit <= 1023.0):
        raise ValueError("rgb_gain_limit must be between 0 and 1023")

    if not (0.0 <= white_balance_speed <= 1.0):
        raise ValueError("white_balance_speed must be between 0 and 1")

    # Use current brightness from FPGA
    spot_r = metering_data['spot_r'] / 255.0
    spot_g = metering_data['spot_g'] / 255.0
    spot_b = metering_data['spot_b'] / 255.0
    matrix_r = metering_data['matrix_r'] / 255.0
    matrix_g = metering_data['matrix_g'] / 255.0
    matrix_b = metering_data['matrix_b'] / 255.0

    spot_average = (spot_r + spot_g + spot_b) / 3.0
    matrix_average = (matrix_r + matrix_g + matrix_b) / 3.0
    center_weighted_average = (spot_average + spot_average + matrix_average) / 3.0

    # Auto exposure based on metering mode
    if metering == "SPOT":
        error = exposure_speed * ((target_exposure / spot_average) - 1) + 1
    elif metering == "CENTER_WEIGHTED":
        error = exposure_speed * ((target_exposure / center_weighted_average) - 1) + 1
    else:  # AVERAGE
        error = exposure_speed * ((target_exposure / matrix_average) - 1) + 1

    # Prevent division by zero by setting a small minimum value
    spot_average = max(spot_average, 0.001)
    matrix_average = max(matrix_average, 0.001)
    center_weighted_average = max(center_weighted_average, 0.001)

    # Get current settings from last state
    last_shutter = last_state["shutter"]
    last_analog_gain = last_state["analog_gain"]
    last_red_gain = last_state["red_gain"]
    last_green_gain = last_state["green_gain"]
    last_blue_gain = last_state["blue_gain"]

    # Adjust exposure - increase shutter first, then gain
    if error > 1:
        shutter = last_shutter
        last_shutter *= error

        if last_shutter > shutter_limit:
            last_shutter = shutter_limit

        error *= shutter / last_shutter

        if error > 1:
            last_analog_gain *= error

            if last_analog_gain > analog_gain_limit:
                last_analog_gain = analog_gain_limit

    # Adjust exposure - decrease gain first, then shutter
    else:
        analog_gain = last_analog_gain
        last_analog_gain *= error

        if last_analog_gain < 1.0:
            last_analog_gain = 1.0

        error *= analog_gain / last_analog_gain

        if error < 1:
            last_shutter *= error

            if last_shutter < 4.0:
                last_shutter = 4.0

    # Convert to integer values for hardware
    shutter = round(last_shutter)
    analog_gain = round(last_analog_gain)

    # shutter/analog gain will be updated after function returns

    # Prevent division by zero in auto white balance
    matrix_r = max(matrix_r, 0.001)
    matrix_g = max(matrix_g, 0.001)
    matrix_b = max(matrix_b, 0.001)
    last_red_gain = max(last_red_gain, 0.001)
    last_green_gain = max(last_green_gain, 0.001)
    last_blue_gain = max(last_blue_gain, 0.001)

    # Auto white balance based on full scene matrix
    # Find the channel with the highest normalized value
    normalized_r = matrix_r / last_red_gain
    normalized_g = matrix_g / last_green_gain
    normalized_b = matrix_b / last_blue_gain
    max_rgb = max(normalized_r, normalized_g, normalized_b)

    # Calculate the gains needed to match all channels to max_rgb
    red_gain = max_rgb / matrix_r * last_red_gain
    green_gain = max_rgb / matrix_g * last_green_gain
    blue_gain = max_rgb / matrix_b * last_blue_gain

    # Calculate scene brightness
    scene_brightness = brightness_constant * (matrix_average / (last_shutter * last_analog_gain))
    print('Scene brightness: ' + str(scene_brightness))

    # Calculate blending factor based on scene brightness
    blending_factor = (scene_brightness - white_balance_min_activation) / (
        white_balance_max_activation - white_balance_min_activation
    )
    print('Blending factor: ' + str(blending_factor))

    # Limit blending factor to valid range
    blending_factor = max(0.0, min(1.0, blending_factor))

    # Apply gradual update to gain values
    last_red_gain = blending_factor * white_balance_speed * (red_gain - last_red_gain) + last_red_gain
    last_green_gain = blending_factor * white_balance_speed * (green_gain - last_green_gain) + last_green_gain
    last_blue_gain = blending_factor * white_balance_speed * (blue_gain - last_blue_gain) + last_blue_gain

    # Scale per-channel gains so the largest channel is at most rgb_gain_limit
    max_rgb_gain = max(last_red_gain, last_green_gain, last_blue_gain)
    if (max_rgb_gain > rgb_gain_limit):
        scale_factor = rgb_gain_limit / max_rgb_gain
        last_red_gain *= scale_factor
        last_green_gain *= scale_factor
        last_blue_gain *= scale_factor

    # Camera registers for white balance will be updated after function returns

    # Prepare return value
    result = {
        "brightness": {
            "spot": {
                "r": spot_r,
                "g": spot_g,
                "b": spot_b,
                "average": spot_average
            },
            "matrix": {
                "r": matrix_r,
                "g": matrix_g,
                "b": matrix_b,
                "average": matrix_average
            },
            "center_weighted_average": center_weighted_average,
            "scene": scene_brightness
        },
        "error": error,
        "shutter": last_shutter,
        "analog_gain": last_analog_gain,
        "red_gain": last_red_gain,
        "green_gain": last_green_gain,
        "blue_gain": last_blue_gain
    }

    # Save state for next call
    last_state.update({
        "shutter": last_shutter,
        "analog_gain": last_analog_gain,
        "red_gain": last_red_gain,
        "green_gain": last_green_gain,
        "blue_gain": last_blue_gain
    })

    return result

async def main():
    """
    Implements a proposed auto exposure and white balance algorithm for Frame that caps per-rgb-channel gain to the specified limit
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
        await frame.upload_stdlua_libs(lib_names=['data', 'camera', 'code'])

        # Send the main lua application from this project to Frame that will run the app
        # to take a photo and send it back when the TxCaptureSettings messages arrive
        await frame.upload_frame_app(local_filename="lua/exposure_wb_frame_app.lua")

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

        # hook up the RxMeteringData receiver
        rx_metering_data = RxMeteringData()
        metering_data_queue = await rx_metering_data.attach(frame)

        # hook up the RxPhoto receiver
        rx_photo = RxPhoto()
        photo_queue = await rx_photo.attach(frame)

        # initialize starting exposure/white balance parameters
        last_state = {
            "shutter": 4096.0,
            "analog_gain": 1.0,
            "red_gain": 121.6,
            "green_gain": 64.0,
            "blue_gain": 140.8
        }

        for i in range(10):
            # send the code to trigger the query for the metering values
            await frame.send_message(0x12, TxCode().pack())

            metering_data = await asyncio.wait_for(metering_data_queue.get(), timeout=10.0)
            print('Metering: ' + str(metering_data))

            algo_result = camera_auto_exposure_algo(metering_data=metering_data,
                                                    last_state=last_state,
                                                    )

            print('Algo Result: ' + str(algo_result))
            print('Last State: ' + str(last_state))

            # take the default manual exposure settings
            tx_manual_exp = TxManualExpSettings(manual_shutter=int(algo_result['shutter']),
                                                manual_analog_gain=int(algo_result['analog_gain']),
                                                manual_red_gain=int(algo_result['red_gain']),
                                                manual_green_gain=int(algo_result['green_gain']),
                                                manual_blue_gain=int(algo_result['blue_gain']),
                                                )

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

        # stop the metering data receiver and clean up its resources
        rx_metering_data.detach(frame)

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