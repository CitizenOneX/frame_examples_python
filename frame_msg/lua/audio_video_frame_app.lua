local data = require('data.min')
local code = require('code.min')
local audio = require('audio.min')
local camera = require('camera.min')

-- Phone to Frame flags
AUDIO_SUBS_MSG = 0x30
CAPTURE_SETTINGS_MSG = 0x0d

-- register the message parsers so they are automatically called when matching data comes in
data.parsers[AUDIO_SUBS_MSG] = code.parse_code
data.parsers[CAPTURE_SETTINGS_MSG] = camera.parse_capture_settings

function clear_display()
    frame.display.text(" ", 1, 1)
    frame.display.show()
    frame.sleep(0.04)
end

function show_flash()
    frame.display.bitmap(241, 191, 160, 2, 0, string.rep("\xFF", 400))
    frame.display.bitmap(311, 121, 20, 2, 0, string.rep("\xFF", 400))
    frame.display.show()
    frame.sleep(0.04)
end

-- Main app loop
function app_loop()
	frame.display.text('Frame App Started', 1, 1)
	frame.display.show()

	local streaming = false
	local last_auto_exp_time = 0

	-- tell the host program that the frameside app is ready (waiting on await_print)
	print('Frame app is running')

	while true do
        rc, err = pcall(
            function()
				-- process any raw data items, if ready
				local items_ready = data.process_raw_items()

				-- one or more full messages received
				if items_ready > 0 then

					if (data.app_data[AUDIO_SUBS_MSG] ~= nil) then

						if data.app_data[AUDIO_SUBS_MSG].value == 1 then
							audio_data = ''
							streaming = true
							audio.start()
							frame.display.text("\u{F0010}", 300, 1)
						else
							-- don't set streaming = false here, it will be set
							-- when all the audio data is flushed
							audio.stop()
							frame.display.text(" ", 1, 1)
						end

						frame.display.show()
						data.app_data[AUDIO_SUBS_MSG] = nil
					end

					if (data.app_data[CAPTURE_SETTINGS_MSG] ~= nil) then
						-- visual indicator of capture and send
						show_flash()
						rc, err = pcall(camera.capture_and_send, data.app_data[CAPTURE_SETTINGS_MSG])
						clear_display()

						if rc == false then
							print(err)
						end

						data.app_data[CAPTURE_SETTINGS_MSG] = nil
					end

				end

				-- send any pending audio data back
				-- Streams until AUDIO_SUBS_MSG is sent from host with a value of 0
				if streaming then
					sent = audio.read_and_send_audio()

					if (sent == nil) then
						streaming = false
					end

					-- 8kHz/8 bit is 8000b/s, which is 33 packets/second, or 1 every 30ms
					frame.sleep(0.005)
				else
					-- not streaming, sleep for longer
					frame.sleep(0.1)
				end

				-- run the autoexposure loop every 100ms
				if camera.is_auto_exp then
					local t = frame.time.utc()
					if (t - last_auto_exp_time) > 0.1 then
						camera.run_auto_exposure()
						last_auto_exp_time = t
					end
				end

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