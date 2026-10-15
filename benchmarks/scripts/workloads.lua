local samples = tonumber(arg[1]) or 7
local count, ticks, iterations = 4096, 256, 1000000
local function numeric()
  local x, sum = 123, 0
  for i = 1, iterations do x = (x * 17 + 31) % 65521; sum = sum + x end
  return sum
end
local function soa()
  local d = {x={}, y={}, vx={}, vy={}, hp={}}
  for j = 1, count do
    local i = j - 1
    d.x[j], d.y[j] = i * 13 % 65521, i * 7 % 65521
    d.vx[j], d.vy[j], d.hp[j] = 1 + i % 7, 1 + i % 11, 100 + i % 100
  end
  return d
end
local function objects()
  local d = {}
  for j = 1, count do
    local i = j - 1
    d[j] = {x=i * 13 % 65521, y=i * 7 % 65521, vx=1 + i % 7, vy=1 + i % 11, hp=100 + i % 100, state=0, cooldown=1 + i % 11}
  end
  return d
end
local function entities_soa(d)
  for tick = 0, ticks - 1 do for j = 1, count do
    d.x[j] = (d.x[j] + d.vx[j]) % 65521
    d.y[j] = (d.y[j] + d.vy[j]) % 65521
    d.hp[j] = (d.hp[j] + tick + j - 1) % 1000
  end end
  local sum = 0; for j = 1, count do sum = sum + d.x[j] + d.y[j] + d.hp[j] end; return sum
end
local function entities_objects(d)
  for tick = 0, ticks - 1 do for j = 1, count do
    local e = d[j]
    e.x = (e.x + e.vx) % 65521; e.y = (e.y + e.vy) % 65521; e.hp = (e.hp + tick + j - 1) % 1000
  end end
  local sum = 0; for j = 1, count do local e = d[j]; sum = sum + e.x + e.y + e.hp end; return sum
end
local function skills(d)
  for tick = 0, ticks - 1 do for j = 1, count do
    local e = d[j]
    if e.state == 0 then
      e.cooldown = e.cooldown - 1; if e.cooldown <= 0 then e.state = 1; e.cooldown = 3 end
    elseif e.state == 1 then e.hp = e.hp - 3; e.state = 2; e.cooldown = 5
    else e.cooldown = e.cooldown - 1; if e.cooldown <= 0 then e.state = 0; e.cooldown = 11 end end
  end end
  local sum = 0; for j = 1, count do local e = d[j]; sum = sum + e.hp + e.state + e.cooldown end; return sum
end
local cases = {
  { 'numeric', function() return numeric end },
  { 'entities-soa', function() local d = soa(); return function() return entities_soa(d) end end },
  { 'entities-objects', function() local d = objects(); return function() return entities_objects(d) end end },
  { 'skills', function() local d = objects(); return function() return skills(d) end end }
}
for _, test in ipairs(cases) do
  local name, prepare = test[1], test[2]
  local expected; for i = 1, 3 do expected = prepare()() end
  local times = {}
  for i = 1, samples do
    local run = prepare(); local start = bench_clock(); local checksum = run(); local ms = (bench_clock() - start) * 1000
    assert(checksum == expected, 'Unstable checksum'); times[#times + 1] = string.format('%.6f', ms)
  end
  print(string.format('{"kind":"result","name":"%s","checksum":%d,"times":[%s]}', name, expected, table.concat(times, ',')))
end
