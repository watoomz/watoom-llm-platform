-- Live channels from Dispatcharr's Web_stream profile, read each time VLC starts.
-- Appears in VLC's playlist sidebar under Internet as "Dispatcharr Web_stream" (enabled by services-discovery=dispatcharr in vlcrc).
-- Local copy of Dispatcharr's Web_stream playlist, refreshed every 5 minutes by watoom-dispatcharr-playlist.timer.
local FILE = "/home/watoom/.local/share/vlc/dispatcharr-web_stream.m3u"

function descriptor()
  return { title = "Dispatcharr Web_stream" }
end

local function fetch()
  local f = io.open(FILE, "r")
  if not f then vlc.msg.warn("dispatcharr: cannot open " .. FILE); return nil end
  local data = f:read("*a") or ""
  f:close()
  vlc.msg.info("dispatcharr: read " .. #data .. " bytes")
  local list, title = {}, nil
  for line in data:gmatch("[^\r\n]+") do
    local t = line:match("^#EXTINF:[^,]*,(.*)$")
    if t then
      title = t
    elseif line:match("^https?://") and title then
      list[#list + 1] = { path = line, title = title }
      title = nil
    end
  end
  return list
end

function main()
  local node = vlc.sd.add_node({ title = "Dispatcharr Web_stream" })
  local list = fetch()
  if not list then return end
  for _, c in ipairs(list) do
    node:add_subitem({ path = c.path, title = c.title, options = { ":network-caching=5000" } })
  end
  vlc.msg.info("dispatcharr: " .. #list .. " channels")
end
