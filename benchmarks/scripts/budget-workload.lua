local function update(state)
  return (state * 1664525 + 1013904223) & 0xffffffff
end

return function()
  local state, checksum = 12345, 0
  for i = 1, 100000 do
    state = update(state)
    checksum = checksum + (state & 255)
  end
  return checksum
end
