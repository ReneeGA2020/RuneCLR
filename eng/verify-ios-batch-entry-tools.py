#!/usr/bin/env python3
"""Exercise the new invocation decoder/reviewer with the fresh offline iOS layout."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--identity', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    driver = Path(__file__).with_name('ios-batch-boundary-entry-capture.py')
    spec = importlib.util.spec_from_file_location('capture', driver)
    capture = importlib.util.module_from_spec(spec); spec.loader.exec_module(capture)
    compile(capture.observer_source(), 'batch_entry_lldb.py', 'exec')
    identity = json.loads(args.identity.read_text())
    config = {'layouts':identity['layouts'], 'author':dict(identity['boundaryAuthor']),
              'requiredMethods':list(identity['boundaryAuthor']['methods']), 'pid':42,
              'entry':identity['symbols']['interpreter']}
    config['author']['path'] = '/owned/late-author/BatchBoundary.Author.dll'
    namespace = {}; exec(compile(capture.DECODER, 'decoder', 'exec'), namespace)
    decode = namespace['decode']
    tests = []

    def fixture(token=0x06000001, mapped='rva'):
        data = {}
        def put(address, value):
            for i, byte in enumerate(value): data[address+i] = byte
        def integer(address, value, size=8): put(address, value.to_bytes(size, 'little'))
        def field(address, kind, member, value, size=8):
            integer(address+config['layouts'][kind]['fields'][member], value, size)
        def memory(address, size):
            try: return bytes(data[address+i] for i in range(size))
            except KeyError: raise RuntimeError('Unmapped synthetic memory')
        context, start, method, chunk, table, module, base = 0x1000,0x2000,0x3000,0x4000,0x5000,0x6000,0x10000
        desc = chunk + config['layouts']['MethodDescChunk']['size'] + 3 * 8
        field(context,'InterpMethodContextFrame','startIp',start); integer(start, method)
        field(method,'InterpMethod','methodHnd',desc); field(method,'InterpMethod','codeSize',16,4)
        field(desc,'MethodDesc','m_chunkIndex',3,1); field(desc,'MethodDesc','m_interpreterCode',start)
        field(desc,'MethodDesc','m_wFlags3AndTokenRemainder',token&0xfff,2)
        field(chunk,'MethodDescChunk','m_flagsAndTokenRange',(token>>12)&0xfff,2)
        field(chunk,'MethodDescChunk','m_methodTable',table); field(table,'MethodTable','m_dwFlags',0x00200000,4)
        field(table,'MethodTable','m_pModule',module); field(module,'Module','m_pSimpleName',0x8000)
        field(module,'Module','m_path',0x9000); put(0x8000,b'BatchBoundary.Author'+bytes(1))
        put(0x9000,config['author']['path'].encode('utf-16-le')+bytes(2))
        field(module,'Module','m_baseAddress',base); field(module,'Module','m_pPEAssembly',0xa000)
        field(module,'Module','m_pAssembly',0xb000)
        root = config['author']['metadataRootRva' if mapped=='rva' else 'metadataRootOffset']
        mvid = config['author']['moduleMvidRva' if mapped=='rva' else 'moduleMvidOffset']
        put(base+root,b'BSJB');put(base+mvid,bytes.fromhex(config['author']['moduleMvidBytesHex']))
        put(start+8,bytes(range(64)))
        return {'memory':memory,'put':put,'field':field,'context':context,'desc':desc,'table':table,'module':module,'base':base,'start':start}

    def reject(label, change):
        f = fixture(); change(f)
        try: decode(f['memory'],f['context'],0,config)
        except RuntimeError: tests.append(label); return
        raise RuntimeError('Invalid native identity accepted: '+label)

    entries = []
    for name, token in config['author']['methods'].items():
        f = fixture(token); item = decode(f['memory'], f['context'], 0, config)
        assert item['metadataMethodName']==name and item['methodDefToken']==token and item['loadedPELayout']=='rva'
        item.update(kind='exact-invocation-entry',pid=42,nativeFilePc=config['entry']['filePc'],nativeModule='libcoreclr.dylib',pc=0x100000)
        entries.append(item)
    capture.verify_entries(entries, config); tests.append('all-four-current-token-identities')
    f = fixture(mapped='flat'); assert decode(f['memory'],f['context'],0,config)['loadedPELayout']=='flat'
    tests.append('flat-loaded-PE-layout')
    f = fixture(); f['field'](f['table'],'MethodTable','m_dwFlags',0,4)
    assert decode(f['memory'],f['context'],0,config) is None; tests.append('noncollectible-prefilter')
    assert decode(lambda a,n: (_ for _ in ()).throw(RuntimeError('must-not-read')),0,1,config) is None
    tests.append('exception-reentry-not-promoted')
    reject('wrong-MVID-rejected',lambda f:f['put'](f['base']+config['author']['moduleMvidRva'],bytes(16)))
    reject('wrong-module-path-rejected',lambda f:f['put'](0x9000,'/other'.encode('utf-16-le')+bytes(2)))
    reject('wrong-MethodDef-rejected',lambda f:f['field'](f['desc'],'MethodDesc','m_wFlags3AndTokenRemainder',99,2))
    reject('wrong-bytecode-owner-rejected',lambda f:f['field'](f['desc'],'MethodDesc','m_interpreterCode',0x1234))
    reject('short-native-memory-rejected',lambda f:f.update(memory=lambda a,n:bytes(max(0,n-1))))
    for label, key, value in (('review-wrong-PID','pid',43),('review-wrong-native-PC','nativeFilePc',1),
                              ('review-wrong-MVID','moduleMvid','other'),('review-noncollectible','collectible',False),
                              ('review-exception-reentry','exceptionArgs',1),('review-wrong-token','methodDefToken',0x060000ff)):
        altered = [dict(e) for e in entries]; altered[0][key] = value
        try: capture.verify_entries(altered, config)
        except RuntimeError: tests.append(label); continue
        raise RuntimeError('Entry reviewer accepted '+label)
    try: capture.verify_entries(entries[:-1],config)
    except RuntimeError: tests.append('review-incomplete-coverage')
    else: raise RuntimeError('Missing method coverage accepted')
    result = {'passed':True,'controls':tests,'driverSha256':hashlib.sha256(driver.read_bytes()).hexdigest(),
              'identitySha256':hashlib.sha256(args.identity.read_bytes()).hexdigest(),
              'observerSha256':hashlib.sha256(capture.observer_source().encode('ascii')).hexdigest(),
              'debuggerStarted':False,'targetProcessCreated':False,'nativeEntryProof':False,
              'scope':'Synthetic bounded reader controls and reviewer rejection paths; no actual invocation evidence.'}
    with args.output.open('x',encoding='ascii') as stream: stream.write(json.dumps(result,indent=2)+chr(10))
    print(json.dumps(result,indent=2))


if __name__ == '__main__':
    main()
