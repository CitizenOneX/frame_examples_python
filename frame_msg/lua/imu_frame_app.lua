local data = require('data.min')
local code = require('code.min')
local imu = require('imu.min')

-- Phone to Frame flags
IMU_SUBS_MSG = 0x40

-- Frame to Phone flags
IMU_DATA_MSG = 0x0A

-- register the message parsers so they are automatically called when matching data comes in
data.parsers[IMU_SUBS_MSG] = code.parse_code

-- Main app loop
function app_loop()
	frame.display.text('Frame App Started', 1, 1)
	frame.display.show()

	local streaming = false

	-- tell the host program that the frameside app is ready (waiting on await_print)
	print('Frame app is running')

	while true do
        rc, err = pcall(
            function()
				-- process any raw data items, if ready
				local items_ready = data.process_raw_items()

				-- one or more full messages received
				if items_ready > 0 then

                    if (data.app_data[IMU_SUBS_MSG] ~= nil) then

                        if data.app_data[IMU_SUBS_MSG].value == 1 then
                            -- start subscription to IMU
                            streaming = true
							frame.display.text('Streaming IMU', 1, 1)
							frame.display.show()
                        else
                            -- cancel subscription to IMU
                            streaming = false
							frame.display.text('Not streaming IMU', 1, 1)
							frame.display.show()
                        end

                        data.app_data[IMU_SUBS_MSG] = nil
                    end

				end

				-- poll and send the raw IMU data (3-axis magnetometer, 3-axis accelerometer)
				-- Streams until STOP_IMU_MSG is sent from host
				if streaming then
					imu.send_imu_data(IMU_DATA_MSG)
				end

				frame.sleep(0.2)
			end
		)
		-- Catch an error (including the break signal) here
		if rc == false then
			-- send the error back on the stdout stream and clear the display
			print(err)
			frame.display.text(' ', 1, 1)
			frame.display.show()
			break
		end
	end
end

-- run the main app loop
app_loop()