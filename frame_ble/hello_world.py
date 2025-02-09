import asyncio
from frame_ble import FrameBle

async def main():
    frame = FrameBle()
    await frame.connect()

    if frame.is_connected():
        await frame.send_lua('frame.display.text("Hello, Frame!", 1, 1);frame.display.show()')
        await frame.disconnect()

    else:
        print("Not connected to Frame")


if __name__ == "__main__":
    asyncio.run(main())