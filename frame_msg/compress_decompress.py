import asyncio
from frame_ble import FrameBle
import lz4.frame

async def main():
    frame = FrameBle()

    try:
        await frame.connect()

        lua_script = """
            function decomp_func(data)
                print(data)
            end

            frame.compression.process_function(decomp_func)

            function ble_func(data)
                frame.compression.decompress(data, 1024)
            end

            frame.bluetooth.receive_callback(ble_func)
        """

        await frame.upload_file_from_string(lua_script, "frame_app.lua")

        await frame.send_lua("require('frame_app');print(0)", await_print=True)

        # set up some sample data (that is highly compressible)
        original_bytes = 100 * "B".encode('utf-8')

        # use the lz4 library to compress
        compressed_data = lz4.frame.compress(original_bytes, compression_level=9)

        # show the amount of compression
        print(f"Original bytes: {len(original_bytes)}")
        print(f"Compressed bytes: {len(compressed_data)}: ({compressed_data.hex()})")

        # print what comes back from Frame, which in this case is the original string
        frame._user_print_response_handler = print

        # send the compressed data to Frame, which will trigger the decompression from the data handler
        # and print it to stdout, which we print with the user_print_response_handler
        await frame.send_data(compressed_data)

        await asyncio.sleep(1)

        await frame.disconnect()

    except Exception as e:
        print(f"Not connected to Frame: {e}")
        return

if __name__ == "__main__":
    asyncio.run(main())