#!/usr/bin/env python3
"""Freeze/check exact private Release build provenance for functional probes."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess

CHECKER_PATH=Path(__file__).with_name('budget-runtime-candidate.py')
_spec=importlib.util.spec_from_file_location('budget_runtime_candidate',CHECKER_PATH)
_candidate=importlib.util.module_from_spec(_spec);_spec.loader.exec_module(_candidate)

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase',choices=('freeze','check'))
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--runtime',type=Path)
    parser.add_argument('--layout',type=Path)
    parser.add_argument('--build-evidence',type=Path)
    parser.add_argument('--candidate-commit',default=_candidate.BASELINE)
    args=parser.parse_args();output=args.output.resolve()
    record=output/'runtime-provenance.json'
    if args.phase=='freeze':
        path=Path(__file__).with_name('benchmark-budget-overhead.py')
        spec=importlib.util.spec_from_file_location('budget_provenance',path)
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        runtime=args.runtime.resolve();layout=args.layout.resolve();evidence=args.build_evidence.resolve()
        validation=_candidate.validate(runtime,args.candidate_commit)
        binding,inputs=module.freeze_build_binding(runtime,layout,'Release',evidence,output,args.candidate_commit)
        for source in (Path(__file__),path):
            frozen=output/'provenance'/source.name;shutil.copy2(source,frozen)
            binding['metadataHashes']['provenance/'+source.name]=sha(frozen)
            inputs[str(source.resolve())]=sha(source)
        value={'passed':True,'runtime':str(runtime),'configuration':'Release','candidateCommit':args.candidate_commit,
               'candidateValidation':validation,'binding':binding,'frozenInputHashes':inputs,
               'scope':'Build/layout/source identity only; runtime behavior and method-entry evidence are separate'}
        record.write_text(json.dumps(value,indent=2)+chr(10))
    else:
        value=json.loads(record.read_text())
        if not value['passed'] or value['configuration']!='Release':raise RuntimeError('Release binding absent')
        if value['binding']['actualSourceCommit']!=args.candidate_commit:
            raise RuntimeError('Explicit candidate does not match frozen Release binding.')
        validation=_candidate.validate(Path(value['runtime']),args.candidate_commit)
        if value.get('candidateValidation',validation)!=validation:
            raise RuntimeError('Frozen Release candidate validation changed.')
        if value['binding'].get('candidateValidation',validation)!=validation:
            raise RuntimeError('Frozen build candidate validation changed.')
        for path,expected in value['frozenInputHashes'].items():
            if sha(path)!=expected:raise RuntimeError('Frozen Release input changed: '+path)
        for path,expected in value['binding']['metadataHashes'].items():
            if sha(output/path)!=expected:raise RuntimeError('Frozen Release metadata changed: '+path)
    print('PASS exact Release native/CoreLib/compiler/source/CMake/layout provenance '+args.phase)

if __name__=='__main__':main()
