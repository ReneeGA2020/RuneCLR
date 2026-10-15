#!/usr/bin/env python3
"""Compose exact batch/CID sources with private indexes and a sparse source-only worktree."""
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
BASE = '0d73c1f21ea32da5ae2d5e1acc4dbb98d0f3e2de'
WINDOWS = 'd0da7dfafc0c4894ae7aa5332ee171f023a0a88e'
PREVIOUS_WINDOWS = '29ff781e157be82ba5a398a60bb05291e4a865af'
OLD_MOBILE = '2d86588f8cef4b3c48ce2ba4d4af15ad7bc83e7c'
OLD_TREE = '3292fc9acf3c15632f3bde34f675caec44f399e2'
BRANCH = 'runeclr/mobile-batch-interval'
CID = 'src/coreclr/vm/virtualcallstub.cpp'
HELPER = ROOT/'eng/mobile-increment-source-proof.py'
CHECKER = ROOT/'eng/batch-interval-runtime-candidate.py'
OLD_PROOF = ROOT/'artifacts/mobile-derived-ledger/source-review-20261014-attempt5/source-proof.json'
PINNED = {
    HELPER: '9e71e5414c222f109e76b702598e5bf9ff48b7d8694e4383e8fee09694540d8d',
    CHECKER: '8ba8eba6d21132f5c4e7837b6ea69a720faf825aa93efe52e00105c4b5ffe31c',
    OLD_PROOF: 'c860e8c483347c8b552b5128d7a5a28f6fe69bef4eb32a2426337a736fddca97',
}


def load(name, path):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def snapshot(helper, repo):
    index=Path(helper.git(repo,'rev-parse','--git-path','index').decode().strip())
    if not index.is_absolute(): index=repo/index
    return {'head':helper.git(repo,'rev-parse','HEAD').decode().strip(),
            'branch':helper.git(repo,'branch','--show-current').decode().strip(),
            'trackedStatus':helper.git(repo,'status','--porcelain','--untracked-files=no').decode(),
            'nativeIndexSha256':helper.sha(index)}


def validate_sources(blobs, hashes):
    if set(blobs)!=set(hashes) or len(blobs)!=38:
        raise ValueError('Exact38 source inventory required.')
    for name,data in blobs.items():
        if b'\r\n' in data or hashlib.sha256(data).hexdigest()!=hashes[name]:
            raise ValueError('Frozen LF source differs: '+name)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime-repo',type=Path,default=Path('E:/runtime-batch-interval-20261014'))
    parser.add_argument('--old-mobile-repo',type=Path,default=Path('E:/runtime-mobile-derived-ledger-20261014'))
    parser.add_argument('--mobile-repo',type=Path,default=Path('E:/runtime-mobile-batch-interval-20261014'))
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--resume-created-commit',help='Resume only the already-created dedicated commit; no branch recreation.')
    args=parser.parse_args()
    repo,old_repo,mobile,output=[p.resolve() for p in (args.runtime_repo,args.old_mobile_repo,args.mobile_repo,args.output)]
    helper=load('mobile_composition_helpers',HELPER)
    checker=load('batch_source_candidate',CHECKER)
    check,git,sha,save=helper.check,helper.git,helper.sha,helper.save
    for path,expected in PINNED.items(): check(sha(path)==expected,'Pinned input changed: '+str(path))
    validation=checker.validate(repo,WINDOWS)
    before,old_before=snapshot(helper,repo),snapshot(helper,old_repo)
    check(old_before['head']==OLD_MOBILE and old_before['branch']=='runeclr/mobile-derived-ledger'
          and not old_before['trackedStatus'],'Exact tracked-clean previous mobile source required.')
    check(not output.exists(),'Fresh source evidence required; preserve existing attempts.')
    branch_probe=subprocess.run(['git','-C',str(repo),'show-ref','--verify','--quiet','refs/heads/'+BRANCH])
    if args.resume_created_commit:
        check(mobile.exists() and branch_probe.returncode==0,'Resume requires the existing dedicated worktree/branch.')
        check(git(mobile,'rev-parse','HEAD').decode().strip()==args.resume_created_commit
              and git(mobile,'branch','--show-current').decode().strip()==BRANCH,
              'Resume must match the exact already-created dedicated commit/branch.')
    else:
        check(not mobile.exists() and branch_probe.returncode==1,'Fresh dedicated worktree/branch required.')
    check(all(not output.is_relative_to(p) for p in (repo,old_repo,mobile)),'Evidence must stay outside source worktrees.')
    output.mkdir(parents=True,exist_ok=False)
    receipts,controls=[],[]
    try:
        shutil.copyfile(__file__,output/'driver.py')
        for path in PINNED:
            name='old-source-proof.json' if path==OLD_PROOF else path.name
            shutil.copyfile(path,output/name)
        old=json.loads(OLD_PROOF.read_text())
        check(old['base']==BASE and old['windowsCommit']==PREVIOUS_WINDOWS and
              old['sourceCommit']==OLD_MOBILE and old['tree']==OLD_TREE and old['changedFileCount']==37,
              'Previous mobile proof identity differs.')
        check(git(repo,'rev-parse',OLD_MOBILE+'^{tree}').decode().strip()==OLD_TREE,'Previous mobile commit tree differs.')
        old_blobs={n:git(repo,'show',OLD_TREE+':'+n) for n in old['sourceHashes']}
        helper.validate_sources(old_blobs,old['sourceHashes'])
        frozen=output/'patches';frozen.mkdir()
        patch_paths={}
        for name,expected in old['patches'].items():
            source=ROOT/'eng/runtime-patches'/name
            check(sha(source)==expected,'Frozen old patch differs: '+name)
            target=frozen/Path(name).name;shutil.copyfile(source,target);patch_paths[name]=target
        batch_patch=frozen/'0011-experimental-batch-interval.patch'
        batch_patch.write_bytes(git(repo,'diff','--binary',PREVIOUS_WINDOWS,WINDOWS))
        cid_patch=patch_paths['0001-collectible-cid-publication.patch']
        save(output/'request.json',{'schema':'runeclr.mobile-batch-interval.source-request.v1',
             'createdUtc':datetime.now(timezone.utc).isoformat(),'base':BASE,'windowsCommit':WINDOWS,
             'oldMobileCommit':OLD_MOBILE,'oldMobileTree':OLD_TREE,'candidateValidation':validation,
             'originalWindows':before,'originalMobile':old_before,'batchPatchSha256':sha(batch_patch),
             'pinnedInputs':{str(p):h for p,h in PINNED.items()},'driverSha256':sha(__file__),
             'plannedSparseWorktree':str(mobile),'nativeBuildRequested':False})
        win_tree=helper.compose(repo,WINDOWS,[cid_patch],output/'windows-cid.index',receipts)
        old_tree=helper.compose(repo,OLD_MOBILE,[batch_patch],output/'old-mobile-batch.index',receipts)
        base_tree=helper.compose(repo,BASE,list(patch_paths.values())+[batch_patch],output/'base-ten-patches.index',receipts)
        check(win_tree==old_tree==base_tree,'Three independent exact mobile batch compositions differ.')
        check(git(repo,'diff','--name-status',WINDOWS,win_tree).decode().splitlines()==['M\t'+CID],
              'Windows-to-mobile delta must only be CID.')
        expected_delta=[('A' if n==checker.STATE else 'M')+'\t'+n for n in sorted(checker.CANDIDATE_HASHES)]
        check(git(repo,'diff','--name-status',OLD_MOBILE,win_tree).decode().splitlines()==expected_delta,
              'Previous-mobile delta must be exactly the four Windows batch files.')
        paths=git(repo,'diff','--name-only',BASE,win_tree).decode().splitlines()
        check(set(paths)==set(old['sourceHashes'])|{checker.STATE},'Only one new state header may extend old37 sources.')
        blobs={n:git(repo,'show',win_tree+':'+n) for n in paths}
        hashes={n:helper.digest(b) for n,b in blobs.items()};validate_sources(blobs,hashes)
        check({n:hashes[n] for n in checker.CANDIDATE_HASHES}==checker.CANDIDATE_HASHES,
              'Mobile batch files differ from exact Windows candidate.')
        for n in old['sourceHashes']:
            if n not in checker.CANDIDATE_HASHES: check(hashes[n]==old['sourceHashes'][n],'Unrelated prior mobile source changed: '+n)
        for n,b in blobs.items():
            target=output/'source'/n;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(b)
        (output/'combined.patch').write_bytes(git(repo,'diff','--binary',BASE,win_tree))
        for label,(n,old_bytes,new_bytes) in checker.MUTANTS.items():
            check(blobs[n].count(old_bytes)==1,'Unique frozen mutation anchor missing: '+label)
            bad=dict(blobs);bad[n]=bad[n].replace(old_bytes,new_bytes,1)
            helper.rejected('source-'+label,lambda bad=bad:validate_sources(bad,hashes),controls)
        for label,n in [('missing-cid',CID),('missing-state',checker.STATE)]:
            bad=dict(blobs);bad.pop(n)
            helper.rejected(label,lambda bad=bad:validate_sources(bad,hashes),controls)
        bad=dict(blobs);bad[checker.METER]=bad[checker.METER].replace(b'\n',b'\r\n')
        helper.rejected('wrong-source-newlines',lambda:validate_sources(bad,hashes),controls)
        for label,start,patches in [('omit-cid',WINDOWS,[]),('omit-batch',OLD_MOBILE,[]),
                                  ('omit-derived',BASE,[p for n,p in patch_paths.items() if '0010' not in n]+[batch_patch])]:
            def wrong_compose(label=label,start=start,patches=patches):
                tree=helper.compose(repo,start,patches,output/('negative-'+label+'.index'),receipts)
                check(tree==win_tree,'Incomplete composition is not the exact mobile candidate.')
            helper.rejected('actual-composition-'+label,wrong_compose,controls)
        interp=blobs[checker.INTERPRETER]
        dispatch_contract={'computedGotoRetainsCharge':b'RUNECLR_CHARGE_DISPATCH(); goto *s_dispatchTable[opcode]' in interp,
                           'switchRetainsCharge':b'SWITCH_OPCODE:\n            // Also covers debugger bypass dispatches that jump to this label.\n            RUNECLR_CHARGE_DISPATCH();\n            switch (opcode)' in interp,
                           'batchHeaderInsideInterpreterFeature':interp.index(b'#ifdef FEATURE_INTERPRETER')<interp.index(b'#include "runeclrbatchstate.h"'),
                           'trapHandlerFlush':b'// The trap can become set after dispatch classified this opcode.\n                        runeclrBatch.Flush();' in interp}
        check(all(dispatch_contract.values()),'Portable dispatch/feature source contract differs.')
        # Sparse checkout writes only the 38 changed sources; full checkout is deferred beyond timing.
        if args.resume_created_commit:
            commit=args.resume_created_commit
            check(git(mobile,'rev-parse','HEAD^{tree}').decode().strip()==win_tree,'Resume tree differs from exact composition.')
            check(git(mobile,'sparse-checkout','list').decode().splitlines()==['/'+n for n in paths],
                  'Existing dedicated sparse patterns differ.')
            existing={p.relative_to(mobile).as_posix():p for p in mobile.rglob('*') if p.is_file() and p.name!='.git'}
            check(set(existing)<=set(paths),'Dedicated worktree contains unexpected files; preserve them.')
            for n,p in existing.items():check(p.read_bytes().replace(b'\r\n',b'\n')==blobs[n],'Existing dedicated source differs: '+n)
        else:
            commit=git(repo,'commit-tree',win_tree,'-p',WINDOWS,'-m','Compose experimental batch interval with collectible CID for mobile').decode().strip()
            git(repo,'update-ref','refs/heads/'+BRANCH,commit,'0'*40)
            git(repo,'-c','core.longpaths=true','worktree','add','--no-checkout',str(mobile),BRANCH)
            git(mobile,'sparse-checkout','init','--no-cone')
            patterns=''.join('/'+n+'\n' for n in paths)
            subprocess.run(['git','-c','core.autocrlf=false','-c','core.longpaths=true','-C',str(mobile),
                            'sparse-checkout','set','--no-cone','--stdin'],input=patterns.encode(),check=True,capture_output=True)
        save(output/'dedicated-worktree.json',{'sourceCommit':commit,'tree':win_tree,'worktree':str(mobile),
             'resumedExistingCommit':bool(args.resume_created_commit),'sparseSourceFileCount':len(paths)})
        git(mobile,'config','--worktree','core.autocrlf','false')
        git(mobile,'config','--worktree','core.eol','lf')
        # --no-checkout creates an empty index; populate it while honoring sparse patterns.
        git(mobile,'-c','core.longpaths=true','-c','core.eol=lf','read-tree','-mu','HEAD')
        check(git(mobile,'rev-list','--parents','-n','1',commit).decode().split()==[commit,WINDOWS],
              'Dedicated mobile commit must have exact Windows direct parent.')
        check(git(mobile,'rev-parse','HEAD^{tree}').decode().strip()==win_tree,'Dedicated mobile tree differs.')
        for n,b in blobs.items():
            source=mobile/n;actual=source.read_bytes()
            check(actual.replace(b'\r\n',b'\n')==b,'Sparse checkout contents differ: '+n)
            if actual!=b:source.write_bytes(b)
            check(source.read_bytes()==b,'Actual sparse mobile LF bytes differ: '+n)
        # Refresh only the exact verified sources; reject any staged content change.
        git(mobile,'add','--',*paths)
        git(mobile,'diff','--cached','--quiet','HEAD')
        check(not git(mobile,'status','--porcelain','--untracked-files=no'),'Dedicated sparse mobile worktree must be tracked clean.')
        check(snapshot(helper,repo)==before and snapshot(helper,old_repo)==old_before,'An existing source/index changed.')
        check(checker.validate(repo,WINDOWS)==validation,'Windows candidate changed during source proof.')
        for p,h in PINNED.items():
            name='old-source-proof.json' if p==OLD_PROOF else p.name
            check(sha(p)==h and sha(output/name)==h,'Pinned tool/proof changed.')
        check(sha(__file__)==sha(output/'driver.py'),'Source proof driver changed during proof.')
        proof={'schema':'runeclr.mobile-batch-interval.source-proof.v1','base':BASE,'windowsCommit':WINDOWS,
               'sourceCommit':commit,'tree':win_tree,'sourceHashes':hashes,'changedFileCount':len(paths),
               'previousMobileCommit':OLD_MOBILE,'previousMobileTree':OLD_TREE,
               'patches':dict(old['patches'])|{'batch-interval/0011-experimental-batch-interval.patch':sha(batch_patch)},
               'compositionTrees':{'windowsPlusCID':win_tree,'previousMobilePlusBatch':old_tree,'basePlusTenPatches':base_tree},
               'privateIndexCompositionVerified':True,'windowsDeltaOnlyCID':True,'previousMobileDeltaOnlyFourBatchFiles':True,
               'exactWindowsBatchFilesVerified':True,'layoutSize':72,'layoutAlignment':8,'batchIntervalOffset':64,
               'batchIntervalDefault':0,'batchIntervalEnvironmentRadix':16,'batchIntervalEnvironmentValues':{'1':'1','100':'64','1000':'3e8'},
               'cleanupAlwaysExact':True,'singleActiveWorkerOvershootBound':'interval - 1',
               'multipleWorkersNotCoveredBySingleWorkerBound':True,'mobileDispatchSourceContracts':dispatch_contract,
               'sourceWorktree':str(mobile),'sourceWorktreeIsSparse':True,'fullCheckoutRequiredBeforeBuild':True,
               'dedicatedWorktreeLineEndingSettings':{'core.autocrlf':'false','core.eol':'lf'},
               'dedicatedIndexTreeStillMatchesHead':True,
               'completeCheckoutCommand':['git','-c','core.autocrlf=false','-c','core.eol=lf','-c','core.longpaths=true','-C',str(mobile),'sparse-checkout','disable'],
               'nativeBuildPerformed':False,'sdkCopied':False,'executionVerified':False,'timingPerformed':False,
               'appleGeneratorPatchIncluded':False,'negativeControls':controls,
               'driverSha256':sha(__file__),'candidateCheckerSha256':sha(CHECKER),
               'previousMobileProofSha256':sha(OLD_PROOF),'requestSha256':sha(output/'request.json'),
               'combinedPatchSha256':sha(output/'combined.patch'),
               'existingTrackedSourcesAndNativeIndexesUnchanged':True,
               'claim':'Exact portable source composition only; no mobile compile, execution, performance or device proof.'}
        save(output/'source-proof.json',proof)
        results={'passed':True,'sourceCommit':commit,'tree':win_tree,'sourceFileCount':len(paths),
                 'patchCount':10,'negativeControlCount':len(controls),'sourceProofSha256':sha(output/'source-proof.json'),
                 'sourceWorktree':str(mobile),'sourceWorktreeIsSparse':True,'nativeBuildPerformed':False,
                 'executionVerified':False,'patchApplications':receipts,'originalWindows':before,'originalMobile':old_before}
        save(output/'results.json',results)
        print(json.dumps({k:v for k,v in results.items() if k not in ('patchApplications','originalWindows','originalMobile')}))
    except Exception as error:
        save(output/'failure.json',{'passed':False,'error':str(error),'patchApplications':receipts,'negativeControls':controls})
        raise


if __name__=='__main__':main()
