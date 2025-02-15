import asyncio
from frame_ble import FrameBle

async def main():
    frame = FrameBle()

    try:
        await frame.connect()

        # stop any application, if running, so we can send lua commands
        await frame.send_break_signal()

        # Keep Frame awake even in charging cradle (for development)
        await frame.send_lua("frame.stay_awake(true);print(0)", await_print=True)
        print("Frame will stay awake - even in the charging cradle - until frame.send_lua('frame.stay_awake(false)')")

        await frame.disconnect()

    except Exception as e:
        print(f"Not connected to Frame: {e}")
        return

if __name__ == "__main__":
    asyncio.run(main())