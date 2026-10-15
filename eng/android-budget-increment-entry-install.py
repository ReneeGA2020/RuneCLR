#!/usr/bin/env python3
"""Install a fresh gated increment APK with bounded bulk immutable transfers."""
import argparse,hashlib,importlib.util,json,re,shutil,subprocess,tarfile,uuid
from pathlib import Path

PARENT_SHA='0bbdd66b80cec5115635a690cd2099df9ed14e1869bd5d518019c540d584c73e'

def adapter():
 p=Path(__file__).with_name('android-budget-increment-apk.py');assert hashlib.sha256(p.read_bytes()).hexdigest()==PARENT_SHA
 spec=importlib.util.spec_from_file_location('candidate_apk',p);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

def inventory(base,args,state,out,name,native_dir):
 base.require(re.fullmatch('[A-Za-z0-9_/+=.~-]+',native_dir),'Unexpected native path')
 targets={}
 for n,h in state['appHashes'].items():
  base.require(re.fullmatch('[A-Za-z0-9_.-]+',n),'Unexpected asset name');targets[native_dir+'/'+n if n.endswith('.so') else 'files/'+n]=(n,h)
 for n,h in state.get('authorHashes',{}).items():
  base.require(re.fullmatch('plugin/[A-Za-z0-9_.-]+',n),'Unexpected author path');targets['files/'+n]=(n,h)
 apk=base.adb(args,['shell','pm','path',state['package']])[0].removeprefix('package:');base.require(re.fullmatch('[A-Za-z0-9_/+=.~-]+/base.apk',apk),'Unexpected APK path');targets[apk]=('apk/base.apk',state['apkSha256'])
 cmd=[str(args.android_root/'sdk/platform-tools/adb.exe'),'-s',args.serial,'exec-out','run-as',state['package'],'sha256sum',*targets]
 q=subprocess.run(cmd,capture_output=True,timeout=60);(out/(name+'.sha256sum.log')).write_bytes(q.stdout);base.require(q.returncode==0,'Bulk inventory command failed');values={};seen=set()
 for l in q.stdout.decode().splitlines():
  if not l.strip():continue
  m=re.fullmatch('([0-9a-f]{64}) +(.+)',l);base.require(m and m[2] in targets and m[2] not in seen,'Inventory path missing/duplicate');key,h=targets[m[2]];base.require(m[1]==h,'Inventory bytes differ '+key);seen.add(m[2]);values[key]=m[1]
 base.require(seen==set(targets),'Inventory missing files');base.write(out/(name+'.json'),values);return values

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);p.add_argument('--inputs',type=Path,required=True);p.add_argument('--android-root',type=Path,default=Path('D:/RuneCLR-Android'));p.add_argument('--serial',default='emulator-5556');p.add_argument('--resume',action='store_true');p.add_argument('--evidence-name',default='bulk-install');a=p.parse_args();module=adapter();base=module.base;module.validate_state(a.output);module.validate_inputs(a.inputs);base.device(a);s=base.load(a.output/'state.json');assert s['installed']==a.resume and not s.get('authorHashes')
 base.require(re.fullmatch('[A-Za-z0-9_-]+',a.evidence_name),'Invalid evidence child name');o=a.output/a.evidence_name;o.mkdir(exist_ok=False);shutil.copy2(__file__,o/'controller.py');started=base.utc()
 if not a.resume:
  text,code=base.adb(a,['install','-r',s['apk']]);base.require(code==0 and 'Success' in text,'Fresh owned gated APK install failed');(o/'install.log').write_text(text);s.update(installed=True,serial=a.serial,installedUtc=base.utc());base.write(a.output/'state.json',s)
 else:
  apk=base.adb(a,['shell','pm','path',s['package']])[0].removeprefix('package:');base.require(base.adb(a,['shell','run-as',s['package'],'sha256sum',apk])[0].split()[0]==s['apkSha256'],'Installed resume APK differs')
 base.adb(a,['shell','run-as',s['package'],'mkdir','-p','files'])
 def transfer(label,sources):
  archive=o/(label+'.tar')
  with tarfile.open(archive,'x') as tar:
   for n,(source,h) in sources.items():
    base.require(re.fullmatch('[A-Za-z0-9_./-]+',n) and '..' not in n,'Invalid owned archive member');base.require(base.sha(source)==h,'Frozen transfer source differs');tar.add(source,arcname=n)
  temp='/data/local/tmp/runeclr-increment-'+uuid.uuid4().hex+'.tar'
  try:base.adb(a,['push',archive,temp]);base.adb(a,['shell','run-as',s['package'],'tar','-xf',temp,'-C','files'])
  finally:base.adb(a,['shell','rm','-f',temp],False)
  return {'archiveSha256':base.sha(archive),'files':{n:h for n,(source,h) in sources.items()}}
 assets=transfer('immutable-assets',{n:(a.output/'app'/n,h) for n,h in s['appHashes'].items() if not n.endswith('.so')})
 appinfo=base.adb(a,['shell','dumpsys','package',s['package']])[0];directories=[line.strip().split('=',1)[1].split()[0] for line in appinfo.splitlines() if line.strip().startswith(('legacyNativeLibraryDir=','nativeLibraryDir='))];base.require(bool(directories),'Native directory absent');paths=base.adb(a,['shell','run-as',s['package'],'find',directories[0],'-name','libcoreclr.so'])[0].splitlines();base.require(len(paths)==1,'Actual native path ambiguous');native_dir=paths[0].rsplit('/',1)[0];inventory(base,a,s,o,'before-author-transfer',native_dir)
 manifest=base.load(a.inputs/'input-manifest.json');author=transfer('postinstall-author',{n:(a.inputs/n,manifest['files'][n]) for n in manifest['authorCollectibleILOnly']});author_dir=a.output/'postinstall-author';author_dir.mkdir(exist_ok=False)
 for n in manifest['authorCollectibleILOnly']:shutil.copy2(a.inputs/n,author_dir/Path(n).name)
 s.update(authorHashes=author['files'],authorTransferredUtc=base.utc());base.write(a.output/'state.json',s);after=inventory(base,a,s,o,'after-author-transfer',native_dir);base.require(len(after)==203,'Actual final immutable input topology differs')
 base.write(a.output/'postinstall-author.json',{'installedUtc':s['installedUtc'],'transferStartedUtc':started,'completedUtc':s['authorTransferredUtc'],'apkSha256':s['apkSha256'],'files':author['files'],'source':'Original unchanged author IL transferred after fresh install'})
 base.write(o/'results.json',{'success':True,'appLaunched':False,'installedEntries':len(after),'assets':assets,'author':author,'driverSha256':base.sha(__file__),'rawHashes':base.files(o)});print('BULK_GATED_INSTALL_PASS',s['package'],len(after))

if __name__=='__main__':main()
