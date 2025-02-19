local data = require('data')
local sprite = require('sprite')

-- Phone to Frame flags
USER_SPRITE = 0x20

-- register the message parsers so they are automatically called when matching data comes in
data.parsers[USER_SPRITE] = sprite.parse_sprite

-- f = function(decompressed)
-- 	print('test')
-- 	--frame.display.bitmap(1, 1, spr.width, 2^spr.bpp, 0, decompressed)
-- 	frame.display.bitmap(1, 1, 634, 2, 0, decompressed)
-- 	--print('called!')
-- end
-- frame.compression.process_function(f)

-- Main app loop
function app_loop()
	frame.display.text('Frame App Started', 1, 1)
	frame.display.show()

	while true do
		local rc, err = pcall(
            function()
				-- process any raw data items, if ready
				local items_ready = data.process_raw_items()

				-- one or more full messages received
				if items_ready > 0 then

					if data.app_data[USER_SPRITE] ~= nil then
						local spr = data.app_data[USER_SPRITE]
						print(spr.compressed)
						print(spr.width)
						print(spr.height)
						print(spr.bpp)
						print(spr.num_colors)
						print(string.len(spr.palette_data))
						print(string.len(spr.pixel_data))
						-- set the palette in case it's different to the standard palette
						sprite.set_palette(spr.num_colors, spr.palette_data)

						-- handle "just in time" decompression for this sprite data
						if spr.compressed then
								-- register the function to call upon decompression
								--frame.compression.process_function(print)
								--frame.compression.process_function(decomp_func)
								frame.compression.process_function(function(decompressed)
									--print('test')
									--print(decompressed)
									frame.display.bitmap(1, 1, spr.width, 2^spr.bpp, 0, decompressed)
									--frame.display.bitmap(1, 1, 634, 2, 0, decompressed)
								end)
								-- decompress as a single block of the full size, handle any padding to whole bytes
								local full_size_bytes = (spr.width * spr.height + ((8 / spr.bpp) - 1)) // (8 / spr.bpp)
								print(full_size_bytes)
								-- decompress and callback will be called
								frame.compression.decompress(spr.pixel_data, full_size_bytes)
								--frame.compression.decompress("\x04\x22\x4d\x18\x64\x40\xa7\x6f\x00\x00\x00\xf5\x3d\x48\x65\x6c\x6c\x6f\x21\x20\x49\x20\x77\x61\x73\x20\x73\x6f\x6d\x65\x20\x63\x6f\x6d\x70\x72\x65\x73\x73\x65\x64\x20\x64\x61\x74\x61\x2e\x20\x49\x6e\x20\x74\x68\x69\x73\x20\x63\x61\x73\x65\x2c\x20\x73\x74\x72\x69\x6e\x67\x73\x20\x61\x72\x65\x6e\x27\x74\x20\x70\x61\x72\x74\x69\x63\x75\x6c\x61\x72\x6c\x79\x3b\x00\xf1\x01\x69\x62\x6c\x65\x2c\x20\x62\x75\x74\x20\x73\x70\x72\x69\x74\x65\x49\x00\xa0\x20\x77\x6f\x75\x6c\x64\x20\x62\x65\x2e\x00\x00\x00\x00\x5f\xd0\xa3\x47", 1024)
						else
								-- raw data, no decompression needed
								frame.display.bitmap(1, 1, spr.width, 2^spr.bpp, 0, spr.pixel_data)
						end

						-- show the sprite
						frame.display.show()

						-- clear the object and run the garbage collector right away
						data.app_data[USER_SPRITE] = nil
						collectgarbage('collect')
					end

				end

				-- can't sleep for long, might be lots of incoming bluetooth data to process
				frame.sleep(0.001)
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