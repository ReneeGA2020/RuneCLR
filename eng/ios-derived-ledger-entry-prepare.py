#!/usr/bin/env python3
"""Read matching new native/DWARF offline; never launch or attach an application."""
import argparse, hashlib, json, re, subprocess
from pathlib import Path

def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p, v): p.write_text(json.dumps(v, indent=2) + chr(10))

READER = '''import json
from pathlib import Path
import lldb
def inspect(debugger):
    c=json.loads(Path(__file__).with_name('request.json').read_text())
    t=debugger.GetSelectedTarget()
    if t.GetProcess().IsValid():raise RuntimeError('offline lane must have no process')
    bp=t.BreakpointCreateByLocation(c['source'],c['dispatchLine'])
    rows=[]
    for loc in bp:
        a=loc.GetAddress()
        ins=t.ReadInstructions(a,12)
        rows.append({'filePc':a.GetFileAddress(),'sourceLine':a.GetLineEntry().GetLine(),
                     'instructions':[{'mnemonic':i.GetMnemonic(t),'operands':i.GetOperands(t)} for i in ins]})
    if not rows:raise RuntimeError('current source dispatch has no DWARF location')
    Path(__file__).with_name('offline-instructions.json').write_text(json.dumps({'processCreated':False,'locations':rows},indent=2)+chr(10))
'''

def main():
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('runtime','native','build-receipt','output'):p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();out=a.output.resolve();out.mkdir(exist_ok=False)
    result={'passed':False,'nativeEntryProof':False,'liveDerivedPathVerified':False,'processCreated':False}
    try:
        b=json.loads(a.build_receipt.read_text());assert b['commit']=='2d86588f8cef4b3c48ce2ba4d4af15ad7bc83e7c' and b['tree']=='3292fc9acf3c15632f3bde34f675caec44f399e2' and b['nativeSha256']==sha(a.native)
        source=a.runtime/'src/coreclr/vm/interpexec.cpp';lines=source.read_text().splitlines()
        anchors=[i for i,l in enumerate(lines) if '// Set execution state for the new frame' in l and 'pMethod = pFrame->startIp->Method;' in lines[i+1] and 'if (stack + pMethod->allocaSize' in chr(10).join(lines[i:i+10])]
        assert len(anchors)==1
        dispatch=[i+1 for i in range(anchors[0],anchors[0]+20) if 'INTOP_NEXT;' in lines[i]];assert len(dispatch)==1
        dwarf=a.native.with_name(a.native.name+'.dwarf');assert dwarf.is_file()
        uuids={}
        for n,file in [('native',a.native),('dwarf',dwarf)]:
            q=subprocess.run(['xcrun','dwarfdump','--uuid',str(file)],text=True,capture_output=True);(out/(n+'-uuid.txt')).write_text(q.stdout+q.stderr);assert q.returncode==0
            found=re.findall('UUID: ([0-9A-Fa-f-]+)',q.stdout);assert len(found)==1;uuids[n]=found[0]
        assert uuids['native']==uuids['dwarf']
        q=subprocess.run(['xcrun','dwarfdump','--name=pFrame',str(dwarf)],text=True,capture_output=True);(out/'pframe-dwarf.txt').write_text(q.stdout+q.stderr);assert q.returncode==0
        request={'source':str(source),'sourceSha256':sha(source),'dispatchLine':dispatch[0],'native':str(a.native),'nativeSha256':sha(a.native),'dwarfSha256':sha(dwarf),'uuid':uuids['native'],'buildReceiptSha256':sha(a.build_receipt),'driverSha256':sha(Path(__file__))}
        write(out/'request.json',request);(out/'offline_reader.py').write_text(READER)
        cmd=['xcrun','lldb','--batch','--no-lldbinit','-o','target create '+str(a.native),'-o','target symbols add '+str(dwarf),'-o','script import sys; sys.path.insert(0, '+repr(str(out))+')','-o','script import offline_reader; offline_reader.inspect(lldb.debugger)']
        write(out/'lldb-request.json',{'command':cmd,'offlineOnly':True})
        q=subprocess.run(cmd,text=True,capture_output=True,timeout=120);(out/'lldb.log').write_text(q.stdout+q.stderr);assert q.returncode==0
        observed=json.loads((out/'offline-instructions.json').read_text());assert observed['processCreated']is False and observed['locations']
        result.update(passed=True,dispatchLine=dispatch[0],locations=observed['locations'],uuid=uuids['native'],scope='Fresh offline native/DWARF/source locations only. Register/PC contract must be reviewed before debugger capture; no app process or live meter/branch samples.')
    except Exception as e:result['error']=str(e);raise
    finally:write(out/'results.json',result);print(json.dumps(result,indent=2))

if __name__=='__main__':main()
