-- TODO switch back to minified
local data = require('data')
local camera = require('camera')
local code = require('code')

-- Phone to Frame flags
METERING_QUERY_MSG = 0x12

-- register the message parser so it's automatically called when matching data comes in
data.parsers[METERING_QUERY_MSG] = code.parse_code

function clear_display()
    frame.display.text(" ", 1, 1)
    frame.display.show()
    frame.sleep(0.04)
end

-- Main app loop
function app_loop()
	clear_display()

	-- tell the host program that the frameside app is ready (waiting on await_print)
	print('Frame app is running')

	while true do
        rc, err = pcall(
            function()
				-- process any raw data items, if ready (parse into take_photo, then clear data.app_data_block)
				local items_ready = data.process_raw_items()

				if items_ready > 0 then

					if (data.app_data[METERING_QUERY_MSG] ~= nil) then
						camera.send_metering_data()
						data.app_data[METERING_QUERY_MSG] = nil
					end

				end

				frame.sleep(0.1)
			end
		)
		-- Catch the break signal here and clean up the display
		if rc == false then
			-- send the error back on the stdout stream
			print(err)
			frame.display.text(" ", 1, 1)
			frame.display.show()
			frame.sleep(0.04)
			break
		end
	end
end

-- run the main app loop
app_loop()