local data = require('data.min')
local code = require('code.min')

-- Phone to Frame flags
AUDIO_SUBS_MSG = 0x30

-- Frame to Phone flags
AUDIO_DATA_FINAL_MSG = 0x06
AUDIO_DATA_NON_FINAL_MSG = 0x05

-- register the message parsers so they are automatically called when matching data comes in
data.parsers[AUDIO_SUBS_MSG] = code.parse_code

-- MOVE to audio.lua
local mtu = frame.bluetooth.max_length()
-- data buffer needs to be even for reading from microphone
if mtu % 2 == 1 then mtu = mtu - 1 end

function start(args)
	pcall(frame.microphone.start, {sample_rate=8000, bit_depth=16})
end

function stop()
	pcall(frame.microphone.stop)
end

-- reads an MTU-sized amount of audio data and sends it to the host
-- ensure this function is called frequently enough to keep up with realtime audio
-- as the Frame buffer is ~32k
function read_and_send_audio()
	audio_data = frame.microphone.read(242)

	-- If frame.microphone.stop() is called, a nil will be read() here
	if audio_data == nil then
		-- send an end-of-stream message back to the host
		while true do
			-- If the Bluetooth is busy, this simply tries again until it gets through
			if (pcall(frame.bluetooth.send, string.char(AUDIO_DATA_FINAL_MSG))) then
				break
			end
			frame.sleep(0.0025)
		end

		return nil

	-- send the data that was read
	elseif audio_data ~= '' then
		while true do
			-- If the Bluetooth is busy, this simply tries again until it gets through
			if (pcall(frame.bluetooth.send, string.char(AUDIO_DATA_NON_FINAL_MSG) .. audio_data)) then
				break
			end
			frame.sleep(0.0025)
		end

		return string.len(audio_data)
	end

	-- no data read, no data sent
	return 0
end


-- Main app loop
function app_loop()
	frame.display.text('Frame App Started', 1, 1)
	frame.display.show()

	local streaming = false

	-- TODO temp?
	local bytes_sent = 0

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
							start({sample_rate=8000, bit_depth=16})
							frame.display.text("\u{F0010}", 1, 1)
						else
							-- don't set streaming = false here, it will be set
							-- when all the audio data is flushed
							stop()
							frame.display.text(" ", 1, 1)
						end

						frame.display.show()
						data.app_data[AUDIO_SUBS_MSG] = nil
					end

				end

				-- send any pending audio data back
				-- Streams until AUDIO_SUBS_MSG is sent from host with a value of 0
				if streaming then
					sent = read_and_send_audio()

					if (sent == nil) then
						streaming = false
					else
						bytes_sent = bytes_sent + sent
					end

					-- 8kHz/16 bit is 16000b/s, which is 66 packets/second, or 1 every 15ms
					frame.sleep(0.01)
				else
					-- not streaming, sleep for longer
					frame.sleep(0.1)
				end
			end
		)
		-- Catch an error (including the break signal) here
		if rc == false then
			-- TODO remove
			print(bytes_sent)
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