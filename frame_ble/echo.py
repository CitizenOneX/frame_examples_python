import asyncio
from frame_ble import FrameBle

async def main():
    frame = FrameBle()

    try:
        await frame.connect()

        # attach the python print function to handle incoming strings from Frame stdout
        frame._user_print_response_handler = print

        # await_print: wait for a print() to ensure the Lua has executed, not just that the command was sent successfully

        # Print literals or computed Lua expressions
        await frame.send_lua("print('echo!')", await_print=True)
        await frame.send_lua("print(5*5*5)", await_print=True)

        # Frame Lua API is available in these commands; see https://docs.brilliant.xyz/frame/building-apps-lua/
        await frame.send_lua("print(frame.FIRMWARE_VERSION)", await_print=True)
        await frame.send_lua("print(frame.battery_level())", await_print=True)

        # "Returns the amount of memory currently used by the program in Kilobytes."
        await frame.send_lua("print(collectgarbage('count'))", await_print=True)

        # Multiple statements are ok
        await frame.send_lua("my_var = 2^8; print(my_var)", await_print=True)

        # receive the printed response synchronously as a returned result from send_lua()
        my_exponent = 10
        response = await frame.send_lua(f"my_var = 2^{my_exponent}; print(my_var)", await_print=True)
        print(f"Answer was: {response}")

        # we can define a global function that persists until a reset
        await frame.send_lua("fib=setmetatable({[0]=0,[1]=1},{__index=function(t,n) t[n]=t[n-1]+t[n-2]; return t[n] end});print(0)", await_print=True)
        my_fib_num = 20
        # and then call it
        fib_answer = await frame.send_lua(f"print(fib[{my_fib_num}])", await_print=True)
        print(f"Fibonacci number {my_fib_num} is: {fib_answer}")

        # If lines of code will be too long to fit in a single bluetooth packet(~240 bytes, depending)
        # then other strategies are needed, including sending Lua files to Frame and then calling their functions.
        # see custom_lua_functions.py for examples.
        # For structured message-passing of images, audio etc. between Frame and host, consider the frame-msg package.

        await frame.disconnect()

    except Exception as e:
        print(f"Not connected to Frame: {e}")
        return

if __name__ == "__main__":
    asyncio.run(main())