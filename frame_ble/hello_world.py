import asyncio
from frame_ble import FrameBle

async def main():
    frame = FrameBle()

    try:
        await frame.connect()

        # wait for a print() to ensure the Lua has executed, not just that the command was sent successfully
        await frame.send_lua("frame.display.text('Hello, Frame!', 1, 1);frame.display.show();print(nil)", await_print=True)

        await frame.disconnect()

    except Exception as e:
        print(f"Not connected to Frame: {e}")
        return

if __name__ == "__main__":
    asyncio.run(main())