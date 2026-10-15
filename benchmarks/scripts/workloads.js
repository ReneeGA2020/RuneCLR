'use strict';
const samples = Number(process.argv[2] || 7);
const count = 4096, ticks = 256, iterations = 1000000;
function numeric() {
  let x = 123, sum = 0;
  for (let i = 0; i < iterations; i++) { x = (x * 17 + 31) % 65521; sum += x; }
  return sum;
}
function soa() {
  const d = {x: new Int32Array(count), y: new Int32Array(count), vx: new Int32Array(count), vy: new Int32Array(count), hp: new Int32Array(count)};
  for (let i = 0; i < count; i++) {
    d.x[i] = i * 13 % 65521; d.y[i] = i * 7 % 65521;
    d.vx[i] = 1 + i % 7; d.vy[i] = 1 + i % 11; d.hp[i] = 100 + i % 100;
  }
  return d;
}
function objects() {
  const d = [];
  for (let i = 0; i < count; i++) d.push({x: i * 13 % 65521, y: i * 7 % 65521, vx: 1 + i % 7, vy: 1 + i % 11, hp: 100 + i % 100, state: 0, cooldown: 1 + i % 11});
  return d;
}
function entitiesSoa(d) {
  for (let tick = 0; tick < ticks; tick++) for (let i = 0; i < count; i++) {
    d.x[i] = (d.x[i] + d.vx[i]) % 65521; d.y[i] = (d.y[i] + d.vy[i]) % 65521; d.hp[i] = (d.hp[i] + tick + i) % 1000;
  }
  let sum = 0; for (let i = 0; i < count; i++) sum += d.x[i] + d.y[i] + d.hp[i]; return sum;
}
function entitiesObjects(d) {
  for (let tick = 0; tick < ticks; tick++) for (let i = 0; i < count; i++) {
    const e = d[i]; e.x = (e.x + e.vx) % 65521; e.y = (e.y + e.vy) % 65521; e.hp = (e.hp + tick + i) % 1000;
  }
  let sum = 0; for (let i = 0; i < count; i++) { const e = d[i]; sum += e.x + e.y + e.hp; } return sum;
}
function skills(d) {
  for (let tick = 0; tick < ticks; tick++) for (let i = 0; i < count; i++) {
    const e = d[i];
    if (e.state === 0) { e.cooldown--; if (e.cooldown <= 0) { e.state = 1; e.cooldown = 3; } }
    else if (e.state === 1) { e.hp -= 3; e.state = 2; e.cooldown = 5; }
    else { e.cooldown--; if (e.cooldown <= 0) { e.state = 0; e.cooldown = 11; } }
  }
  let sum = 0; for (let i = 0; i < count; i++) { const e = d[i]; sum += e.hp + e.state + e.cooldown; } return sum;
}
const cases = [
  ['numeric', () => numeric],
  ['entities-soa', () => { const d = soa(); return () => entitiesSoa(d); }],
  ['entities-objects', () => { const d = objects(); return () => entitiesObjects(d); }],
  ['skills', () => { const d = objects(); return () => skills(d); }]
];
for (const [name, prepare] of cases) {
  let expected; for (let i = 0; i < 3; i++) expected = prepare()();
  const times = [];
  for (let i = 0; i < samples; i++) {
    const run = prepare(), start = process.hrtime.bigint();
    const checksum = run(), ms = Number(process.hrtime.bigint() - start) / 1e6;
    if (checksum !== expected) throw new Error('Unstable checksum'); times.push(ms);
  }
  console.log(JSON.stringify({kind: 'result', name, checksum: expected, times}));
}
