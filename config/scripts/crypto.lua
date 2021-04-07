local msg = require 'mp.msg'

local function on_start()
    local streamOpenFN = mp.get_property_native("stream-open-filename")
    if (type(streamOpenFN) ~= "string") then do return end end
    msg.log("info", "open file: " .. streamOpenFN)
    local file = io.open(streamOpenFN,"rb")
    if not file then return nil end
    local block = file:read(8)
    file:close()
    if (block == 'EV000001')
    then
        msg.log("info", "crypto marker: EV000001")
        mp.set_property(
            "stream-open-filename",
            "crypto:///" .. streamOpenFN
        )
        msg.log("info", "stream-open-filename: crypto:///" .. streamOpenFN)
    end
end

mp.add_hook("on_load", 50, on_start)