import asyncio
from frame_ble import FrameBle

async def main():
    frame = FrameBle()

    try:
        await frame.connect()

        # stop any application, if running, so we can send lua commands
        await frame.send_break_signal()

        # Restore normal behavior that Frame turns off when placed in the charging cradle (and puts it to sleep now)
        await frame.send_lua("frame.stay_awake(false);print(0)", await_print=True)
        await frame.send_lua("frame.sleep()", await_print=False)
        print("Frame will switch off when placed in the charging cradle, and will be put to sleep now (tap to wake)")

        await frame.disconnect()

    except Exception as e:
        print(f"Not connected to Frame: {e}")
        return

if __name__ == "__main__":
    asyncio.run(main())