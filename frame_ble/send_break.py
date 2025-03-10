import asyncio
from frame_ble import FrameBle

async def main():
    frame = FrameBle()

    try:
        await frame.connect()

        # stop any application, if running, so we can send lua commands
        await frame.send_break_signal()
        print("Break sent")

        await frame.disconnect()

    except Exception as e:
        print(f"Not connected to Frame: {e}")
        return

if __name__ == "__main__":
    asyncio.run(main())