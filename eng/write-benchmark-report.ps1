param([Parameter(Mandatory)][string]$Results)
$ErrorActionPreference = 'Stop'
$json = Get-Content $Results -Raw
$null = $json | ConvertFrom-Json
$template = @'
<!doctype html>
<html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>RuneCLR 本地性能对比</title>
<style>
:root{color-scheme:light;--ink:#182331;--muted:#536477;--line:#dce3e9;--accent:#176458}
*{box-sizing:border-box}body{margin:0;background:#f3f6f8;color:var(--ink);font:16px/1.6 system-ui,"Microsoft YaHei",sans-serif}
main{max-width:960px;margin:auto;padding:28px 18px 44px}h1{font-size:28px;line-height:1.3;margin:0 0 12px}h2{font-size:20px;margin:0 0 12px}
p{margin:10px 0}.muted,small{color:var(--muted)}.card{background:white;border:1px solid var(--line);border-radius:16px;padding:22px;margin:18px 0}
.lead{border-left:5px solid var(--accent)}select{font:inherit;padding:8px;border-radius:8px;border:1px solid var(--line);max-width:100%;background:white}
.controls{display:flex;gap:14px;flex-wrap:wrap;margin:16px 0}label{display:grid;gap:5px}.row{margin:16px 0}.rowhead{display:flex;justify-content:space-between;gap:12px;font-size:14px}.track{height:15px;background:#eef2f5;border-radius:5px;margin:5px 0}.bar{height:100%;background:#698197;border-radius:5px;min-width:2px}.primary .bar{background:var(--accent)}.primary .rowhead{font-weight:700}
.tablewrap{overflow-x:auto}table{width:100%;border-collapse:collapse;white-space:nowrap;font-size:14px}th,td{text-align:right;padding:10px 12px;border-bottom:1px solid var(--line)}th:first-child,td:first-child{text-align:left}th{background:#f5f8fa}code{font-size:13px;overflow-wrap:anywhere}.foot{font-size:14px}button{border:0;border-radius:7px;background:var(--accent);color:white;padding:9px 15px;font:inherit}
@media(max-width:500px){main{padding:20px 12px}.card{padding:16px}h1{font-size:25px}.rowhead{font-size:13px}}
</style>
<main>
<p class="muted">RuneCLR · Windows x64 本地实验</p><h1>解释执行，实际慢多少？</h1>
<div class="card lead"><p><strong id="conclusion"></strong></p><p>解释和 JIT 的差距应结合真实玩法判断。现有 JIT 玩法迁移到解释执行时，需要单独做性能预算。</p><small>这里的差距是本机、这些负载的测量结果。小差异需要结合各轮波动判断，不能推断为跨平台的固定优势。</small></div>
<p id="machine" class="muted"></p>
<div class="card"><h2>切换负载比较</h2><p>条形越长，耗时越多。每次实体测试包含 4096 个实体 × 256 次更新，不能直接把整段耗时当作一帧耗时。</p>
<div class="controls"><label>负载<select id="case"><option value="numeric">数值循环 · 100 万次</option><option value="entities-soa">实体更新 · 分离数组</option><option value="entities-objects">实体更新 · 对象字段</option><option value="skills">技能状态机 · 对象字段</option></select></label><label>显示方式<select id="unit"><option value="ms">耗时中位数（毫秒）</option><option value="ratio">相对 Lua 耗时（Lua = 1）</option></select></label></div>
<div id="bars"></div><p id="detail" class="foot muted"></p></div>
<div class="card"><h2>完整数据</h2><div class="tablewrap"><table><thead><tr><th>负载</th><th>C# 解释</th><th>Lua 5.4</th><th>JS 纯解释</th><th>C# JIT</th><th>JS JIT</th></tr></thead><tbody id="table"></tbody></table></div><p id="method" class="foot muted"></p></div>
<div class="card"><h2>怎样理解这些数字</h2><p>各负载预热后再测量。数据初始化、进程启动、方法入口检测和日志在计时之外；计时包含逻辑执行及最终校验和。V8 保留默认分层 JIT，测量期间仍可能继续优化或反优化，不能保证编译开销全部被排除。所有引擎的校验和一致。</p><p>C# 解释和 JIT 使用相同的 Release CoreCLR 与同一份测试 IL。解释只选择测试逻辑程序集，宿主保持原生执行；方法入口检测确认了实际解释路径。没有修改 CoreCLR 源码，也没有安装替换系统运行时。</p><p>C# 分离数组使用 int[]，JS 使用 Int32Array，Lua 使用普通表；对象负载使用 C# 类、JS 对象、Lua 表。它们是相应语言的直接实现，不是相同的内存布局。</p><p>这轮没有测宿主绑定、分配密集逻辑、GC 尾延迟、地图加载卸载耗时或强制预算检查开销，也不代表 iOS/Android 实机表现。</p><p id="versions" class="foot muted"></p><button id="download">下载原始 JSON 数据</button></div>
<p class="foot muted">本报告为自包含单文件，所有图表和数据都可离线查看。</p>
</main>
<script type="application/json" id="data">__DATA__</script>
<script>
const data=JSON.parse(document.getElementById('data').textContent);
const labels={'coreclr-interpreter':'C# / CoreCLR 解释','coreclr-jit':'C# / CoreCLR JIT','lua-5.4':'Lua 5.4.9','javascript-jit':'JavaScript / V8 JIT','javascript-jitless':'JavaScript / V8 纯解释'};
const names={'numeric':'数值循环','entities-soa':'实体更新 · 分离数组','entities-objects':'实体更新 · 对象字段','skills':'技能状态机'};
const engines=['coreclr-interpreter','lua-5.4','javascript-jitless','coreclr-jit','javascript-jit'];
const gameplay=data.summary.filter(x=>x.engine==='coreclr-interpreter'&&x.case!=='numeric').map(x=>x.timeRelativeToLua);
document.getElementById('conclusion').textContent='实体更新和状态机：CoreCLR 解释耗时为 Lua 的 '+Math.min(...gameplay).toFixed(2)+'～'+Math.max(...gameplay).toFixed(2)+' 倍；数值循环为 '+data.summary.find(x=>x.engine==='coreclr-interpreter'&&x.case==='numeric').timeRelativeToLua.toFixed(2)+' 倍。';
document.getElementById('method').textContent='单位：毫秒；'+data.rounds+' 个独立进程，每个负载先预热 '+data.warmups+' 次，再测 '+data.samples+' 次，合计 '+(data.rounds*data.samples)+' 个样本。表格取全部样本的中位数。';
document.getElementById('machine').textContent=data.cpu+' · '+data.os+' · '+data.date.slice(0,10);
document.getElementById('versions').textContent='CoreCLR '+data.runtimeBase.slice(0,12)+' · Release / FEATURE_INTERPRETER=1 · Node '+data.node+' / V8 '+data.v8+' · '+data.lua;
function draw(){
  const key=document.getElementById('case').value,ratio=document.getElementById('unit').value==='ratio';
  const rows=data.summary.filter(x=>x.case===key),field=ratio?'timeRelativeToLua':'medianMs',max=Math.max(...rows.map(x=>x[field]));
  const container=document.getElementById('bars');container.replaceChildren();
  for(const engine of engines){
    const r=rows.find(x=>x.engine===engine),row=document.createElement('div');row.className='row'+(engine==='coreclr-interpreter'?' primary':'');
    const head=document.createElement('div');head.className='rowhead';
    const label=document.createElement('span');label.textContent=labels[engine];const value=document.createElement('span');value.textContent=r[field].toFixed(2)+(ratio?' × Lua 耗时':' ms');head.append(label,value);
    const track=document.createElement('div');track.className='track';const bar=document.createElement('div');bar.className='bar';bar.style.width=(r[field]/max*100)+'%';track.append(bar);row.append(head,track);container.append(row);
  }
  const r=rows.find(x=>x.engine==='coreclr-interpreter');
  document.getElementById('detail').textContent='C# 解释：各轮中位数 '+r.roundMedians.map(x=>x.toFixed(2)).join(' / ')+' ms；所有样本范围 '+r.minMs.toFixed(2)+'～'+r.maxMs.toFixed(2)+' ms。';
}
for(const key of Object.keys(names)){
  const tr=document.createElement('tr'),td=document.createElement('td');td.textContent=names[key];tr.append(td);
  for(const engine of engines){const cell=document.createElement('td');cell.textContent=data.summary.find(x=>x.case===key&&x.engine===engine).medianMs.toFixed(2);tr.append(cell);}
  document.getElementById('table').append(tr);
}
document.getElementById('case').addEventListener('change',draw);document.getElementById('unit').addEventListener('change',draw);draw();
document.getElementById('download').addEventListener('click',()=>{const url=URL.createObjectURL(new Blob([JSON.stringify(data,null,2)],{type:'application/json'}));const a=document.createElement('a');a.href=url;a.download='runeclr-benchmark-results.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);});
</script></html>
'@
$destination = Join-Path (Split-Path (Resolve-Path $Results) -Parent) 'report.html'
$template.Replace('__DATA__', $json.Replace('</', '<\/')) | Set-Content $destination -Encoding utf8
Write-Host ('Report: ' + $destination)
