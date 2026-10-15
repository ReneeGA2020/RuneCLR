param([Parameter(Mandatory)][string]$Results)
$ErrorActionPreference = 'Stop'
$resolved = (Resolve-Path -LiteralPath $Results).ProviderPath
$json = Get-Content -LiteralPath $resolved -Raw
$data = $json | ConvertFrom-Json
if (!$data.summary -or !$data.raw) { throw 'Results must contain summary and raw benchmark records.' }
$template = @'
<!doctype html>
<html lang="zh-CN">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>RuneCLR · 宿主调用、地图会话与内存实验</title>
<style>
:root{color-scheme:light;--ink:#1d2937;--muted:#5b6978;--line:#dde5ea;--green:#166459;--blue:#536d9b;--bg:#f3f6f8}*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.65 system-ui,"Microsoft YaHei",sans-serif}main{max-width:1000px;margin:auto;padding:28px 20px 50px}h1{font-size:30px;line-height:1.35;margin:6px 0 12px}h2{font-size:22px;margin:0 0 12px}h3{font-size:18px;margin:0 0 7px}p{margin:10px 0}.muted,small{color:var(--muted)}small{font-size:13px}.card{background:white;border:1px solid var(--line);border-radius:15px;padding:23px;margin:18px 0}.lead{border-left:5px solid var(--green)}.controls{display:flex;align-items:center;gap:12px;flex-wrap:wrap;position:sticky;top:0;background:var(--bg);padding:12px 0;z-index:2}select,button{font:inherit;border-radius:8px;padding:8px 12px;border:1px solid var(--line);background:white}button{color:white;background:var(--green);cursor:pointer}.pair{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-top:16px}.engine{background:#f5f8fa;border-radius:10px;padding:15px}.engine.primary{background:#edf6f3}.enginehead{display:flex;align-items:baseline;justify-content:space-between;gap:12px}.number{font-size:25px;font-weight:700;white-space:nowrap}.track{height:12px;background:#dfe7ed;border-radius:5px;margin:10px 0}.bar{height:100%;background:var(--blue);border-radius:5px;min-width:2px}.primary .bar{background:var(--green)}.stats{font-size:14px}.stats p{margin:6px 0}.note{font-size:14px;color:var(--muted)}.round{border-top:1px solid var(--line);padding-top:12px;margin-top:14px}.roundtitle{font-weight:700;font-size:15px}.tablewrap{overflow-x:auto}table{border-collapse:collapse;width:100%;font-size:14px;white-space:nowrap}th,td{padding:8px 9px;border-bottom:1px solid var(--line);text-align:right}th:first-child,td:first-child{text-align:left}th{color:var(--muted);font-weight:500}.pill{display:inline-block;background:#e9f3ef;color:#15584e;border-radius:20px;padding:3px 10px;font-size:13px}code{font-size:13px;overflow-wrap:anywhere}.foot{font-size:14px}.hidden{display:none}
@media(max-width:620px){main{padding:20px 12px 36px}h1{font-size:25px}.card{padding:17px}.pair{grid-template-columns:1fr;gap:12px}.engine{padding:13px}h2{font-size:20px}.number{font-size:23px}th,td{padding:8px 6px}.controls{padding:10px 0}}
#source,#cold-scope{overflow-wrap:anywhere}
</style></head>
<body><main>
<p class="muted">RuneCLR · Release CoreCLR 本地性能实验</p>
<h1>宿主调用、地图会话与回收成本</h1>
<p id="machine" class="muted"></p>
<div class="card lead"><p><strong>纯负载与完整会话测的是不同阶段，不能直接互相替代。</strong></p><p>纯负载先预热，完整会话每次创建新的可回收加载上下文，包含加载、首次编译、回调、停止与卸载请求。短会话中解释耗时较低，不代表解释执行具有稳态性能优势。</p><p id="protocol" class="note"></p></div>
<div class="controls"><label for="view">显示范围</label><select id="view"><option value="all">全部</option><option value="pure">纯负载</option><option value="sessions">真实会话</option></select><small>耗时单位：毫秒；越小越快</small></div>
<div id="pure" data-group="pure"><h2>预热后的纯负载</h2><p class="note">每个进程先预热 3 次。准备数据和初始化存储在计时外；调用逻辑、宿主操作及校验在计时内。分配仅统计当前线程计时区间，包含该线程上的宿主与框架分配，不能视为地图独占内存。</p><div id="pure-cases"></div></div>
<div id="sessions" data-group="sessions"><h2>真实地图会话</h2><p class="note">使用真实 MapRunner 和 IMapContext。每个样本重新加载地图，开始、执行全部指定 ticks、停止，并请求卸载；不包含等待加载上下文被 GC 回收的时间。这里的 128 ticks 是一整局的测试量，不能把总耗时当作单帧耗时。</p><div id="session-cases"></div></div>
<div id="cold" data-group="sessions"><h2>冷进程到退出</h2><p class="note">每个样本启动独立进程，包含启动、manifest 读取、首张空地图、JSON 输出和输出流收集。OS 文件缓存未刷新，因此不是冷磁盘启动。具体启动器计时范围见下方原始记录。</p><div id="cold-cases"></div><p id="cold-scope" class="note"></p></div>
<div id="retention" data-group="sessions"><h2>连续地图之后，内存是否回落？</h2><p class="note">每轮连续执行 40 个 gameplay 会话，每次 128 ticks，中途不强制 GC。三个快照分别在开始前、全部会话之后、调用栈返回后的诊断 GC 之后。managed 是托管对象估计量；private 是进程私有内存，包含运行时、堆保留空间和原生分配。</p><div id="retention-cards"></div><div class="card lead"><p><strong>强制 GC 是回收诊断，不是生产环境的逐帧策略。</strong></p><p>卸载请求之后暂未被收集，不足以判定泄漏。诊断 GC 后托管内存回落、加载上下文被收集，也不意味着进程私有内存立即归零或回到开始值；仍需要更长运行和真实设备验证。</p></div></div>
<div class="card"><h2>实验边界与复现信息</h2><p>解释与 JIT 使用同一份地图 IL、同一私有 Release 运行时。仅 UGC 方法选择解释执行，可信宿主和框架保持原生；方法入口探针确认实际路径。R2R 和分层编译关闭，这是一组受控开发对照，不代表生产配置。</p><p>GC 计数为进程级统计，分配字节为当前线程计时区间统计。少量样本不能建立 GC 尾延迟、内存隔离或跨设备性能结论。测试未包含强制预算检查，也不证明 iOS／Android 支持。</p><p id="runtime" class="note"></p><p id="source" class="note"></p><button id="download">下载原始 JSON</button></div>
<p class="foot muted">本报告为自包含单文件，全部数据与图表可离线查看。</p>
</main>
<script type="application/json" id="data">__DATA__</script>
<script>
'use strict';
const data=JSON.parse(document.getElementById('data').textContent);
const engines=['coreclr-interpreter','coreclr-jit'];
const engineNames={'coreclr-interpreter':'C# 解释','coreclr-jit':'C# JIT'};
const names={'host-api':'宿主 API 边界','allocations-generics':'分配与泛型集合','empty-session':'空地图 · 0 ticks','gameplay-start':'玩法地图 · 0 ticks','gameplay-128-ticks':'玩法地图 · 128 ticks','cold-process-to-exit':'独立进程 · 首张空地图到退出'};
const descriptions={'host-api':'131,072 次实体创建／销毁和显式 Charge，2,048 次日志调用。使用真实共享接口的可信基准适配器；宿主存储预先分配。','allocations-generics':'256 批 × 128 个值；分配 Dictionary、List 和字符串，调用闭合泛型求和方法。','empty-session':'加载空地图并调用 OnStart／OnStop，作为最小完整生命周期基线。','gameplay-start':'初始化 64 个常驻实体与泛型集合；随后停止，由宿主回收实体。','gameplay-128-ticks':'初始化后执行 128 次更新；每 tick 创建并销毁 8 个临时实体，分配 4 组泛型列表。'};
const byId=id=>document.getElementById(id);
const fmt=value=>Number.isFinite(value)?value.toFixed(3):'—';
const bytes=value=>!Number.isFinite(value)?'—':value===0?'0 B':value<1024?value.toFixed(0)+' B':value<1048576?(value/1024).toFixed(2)+' KiB':(value/1048576).toFixed(2)+' MiB';
const median=values=>{const sorted=[...values].sort((a,b)=>a-b);return sorted.length?sorted.length%2?sorted[(sorted.length-1)/2]:(sorted[sorted.length/2-1]+sorted[sorted.length/2])/2:NaN;};
function node(tag,text,className){const el=document.createElement(tag);if(text!==undefined)el.textContent=text;if(className)el.className=className;return el;}
byId('machine').textContent=[data.cpu,data.os,data.arch,(data.date||'').slice(0,10)].filter(Boolean).join(' · ');
byId('protocol').textContent=data.rounds+' 轮独立进程，每轮每项 '+data.samples+' 个样本。显示全部样本的中位数、最小值和最大值；每个条形只在本负载内缩放。';
byId('runtime').textContent='CoreCLR '+(data.runtimeBase||'').slice(0,12)+' · '+(data.runtimeConfiguration||'Release')+' · SDK '+data.sdk+' · 宿主 '+(data.hostCommit||'').slice(0,12);
byId('source').textContent='原始证据目录：'+data.evidenceDirectory;
byId('cold-scope').textContent='计时范围原文：'+data.coldScope;
function drawCase(name,target){
  const rows=data.summary.filter(row=>row.name===name);if(!rows.length)return;
  const card=node('section',undefined,'card');card.append(node('h3',names[name]||name));
  if(descriptions[name])card.append(node('p',descriptions[name],'note'));
  const pair=node('div',undefined,'pair'),scale=Math.max(...rows.map(row=>row.medianMs));
  for(const engine of engines){
    const row=rows.find(item=>item.engine===engine);if(!row)continue;
    const block=node('div',undefined,'engine'+(engine==='coreclr-interpreter'?' primary':''));
    const head=node('div',undefined,'enginehead');head.append(node('strong',engineNames[engine]),node('span',fmt(row.medianMs)+' ms','number'));
    const track=node('div',undefined,'track'),bar=node('div',undefined,'bar');bar.style.width=(scale>0?row.medianMs/scale*100:0)+'%';track.append(bar);block.append(head,track);
    const stats=node('div',undefined,'stats');stats.append(node('p','样本范围 '+fmt(row.minMs)+'～'+fmt(row.maxMs)+' ms · '+row.samples+' 个样本'));
    const raw=data.raw.filter(item=>item.engine===engine&&(name==='cold-process-to-exit'?item.record.kind==='cold':item.record.name===name));
    const allocations=name==='cold-process-to-exit'?raw.map(item=>item.record.allocatedBytes):raw.flatMap(item=>item.record.allocatedBytes||[]);
    const allocation=Number.isFinite(row.medianAllocatedBytes)?row.medianAllocatedBytes:median(allocations);
    stats.append(node('p',(name==='cold-process-to-exit'?'首图计时区间分配':'计时区间分配')+'中位数 '+bytes(allocation)));
    if(allocations.length)stats.append(node('p','分配范围 '+bytes(Math.min(...allocations))+'～'+bytes(Math.max(...allocations))));
    if(row.roundMedians)stats.append(node('p','各轮中位数 '+row.roundMedians.map(fmt).join(' / ')+' ms'));
    if(Number.isFinite(row.medianFirstMapMs))stats.append(node('p','其中首图 MapRunner.Run 中位数 '+fmt(row.medianFirstMapMs)+' ms（未含启动和 manifest 读取）'));
    const counts=name==='cold-process-to-exit'?raw.map(item=>item.record.gcCounts):raw.flatMap(item=>item.record.gcCounts||[]);
    const totals=[0,0,0];for(const sample of counts)if(Array.isArray(sample))for(let generation=0;generation<3;generation++)totals[generation]+=sample[generation]||0;
    stats.append(node('p','所有计时样本 GC 次数合计：Gen0 / Gen1 / Gen2 = '+totals.join(' / ')));
    block.append(stats);pair.append(block);
  }
  card.append(pair);byId(target).append(card);
}
for(const name of ['host-api','allocations-generics'])drawCase(name,'pure-cases');
for(const name of ['empty-session','gameplay-start','gameplay-128-ticks'])drawCase(name,'session-cases');
drawCase('cold-process-to-exit','cold-cases');
for(const engine of engines){
  const rows=data.raw.filter(item=>item.engine===engine&&item.record.kind==='retention').sort((a,b)=>a.round-b.round);
  if(!rows.length)continue;
  const card=node('section',undefined,'card');card.append(node('h3',engineNames[engine]+' · 各轮内存快照'));
  for(const item of rows){
    const record=item.record,round=node('div',undefined,'round');round.append(node('div','第 '+item.round+' 轮 · '+record.sessions+' 次会话 × '+record.ticksPerSession+' ticks','roundtitle'));
    const wrap=node('div',undefined,'tablewrap'),table=node('table'),thead=node('thead'),heading=node('tr');for(const label of ['时点','托管对象','进程私有内存'])heading.append(node('th',label));thead.append(heading);table.append(thead);
    const tbody=node('tbody');for(const [key,label] of [['before','开始前'],['afterSessions','会话之后'],['afterDiagnosticGc','诊断 GC 后']]){const snapshot=record[key],tr=node('tr');tr.append(node('td',label),node('td',bytes(snapshot.managedBytes)),node('td',bytes(snapshot.privateBytes)));tbody.append(tr);}table.append(tbody);wrap.append(table);round.append(wrap);
    round.append(node('p','已收集加载上下文：诊断 GC 前 '+record.collectedBefore+' / '+record.sessions+' → 诊断 GC 后 '+record.collectedAfter+' / '+record.sessions,'pill'));
    round.append(node('p','托管对象变化：会话之后 '+bytes(record.afterSessions.managedBytes-record.before.managedBytes)+'；诊断 GC 后相对开始 '+bytes(record.afterDiagnosticGc.managedBytes-record.before.managedBytes),'note'));card.append(round);
  }
  byId('retention-cards').append(card);
}
byId('view').addEventListener('change',()=>{const choice=byId('view').value;for(const section of document.querySelectorAll('[data-group]'))section.classList.toggle('hidden',choice!=='all'&&section.dataset.group!==choice);});
byId('download').addEventListener('click',()=>{const url=URL.createObjectURL(new Blob([JSON.stringify(data,null,2)],{type:'application/json'}));const link=node('a');link.href=url;link.download='runeclr-session-results.json';link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);});
</script></body></html>
'@
# Escape all HTML-significant characters, including any case of </script>.
# JSON remains valid inside the data block and is only rendered via textContent.
$safeJson = $json.Replace('<', '\u003c').Replace('>', '\u003e').Replace('&', '\u0026').
    Replace([string][char]0x2028, '\u2028').Replace([string][char]0x2029, '\u2029')
$destination = Join-Path (Split-Path -Path $resolved -Parent) 'report.html'
$template.Replace('__DATA__', $safeJson) | Set-Content -LiteralPath $destination -Encoding utf8
Write-Host ('Report: ' + $destination)
