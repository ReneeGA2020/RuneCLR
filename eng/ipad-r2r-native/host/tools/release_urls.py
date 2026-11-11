#!/usr/bin/env python3
"""Print the delivery URLs and environment block for one sealed release directory.

Reads a directory produced by PackageSealer.Seal (payload-files.txt, runeclr.compat.json,
runeclr.release.json) and emits the host-side configuration for a device launch. It does not
sign, copy, or contact the device; it only prints what the host must be given.

Usage:
    python3 -B eng/ipad-r2r-native/host/tools/release_urls.py \
        --root /path/to/served/<version> --base-url http://192.0.2.10:8099/<version> \
        --version A [--json]
"""
import argparse
import json
import os
import sys

DOCUMENT = 'runeclr.release.json'
SIDECAR = 'runeclr.compat.json'
PAYLOAD_LIST = 'payload-files.txt'


def read_payload_list(root):
    path = os.path.join(root, PAYLOAD_LIST)
    names = []
    with open(path, 'r', encoding='utf-8') as handle:
        for raw in handle:
            line = raw.strip()
            if not line:
                continue
            parts = line.split()
            if len(parts) != 2 or len(parts[0]) != 64:
                raise SystemExit('payload-files.txt is not <sha256>  <name>: ' + line[:80])
            name = parts[1]
            if '/' in name or '\\' in name or name in ('.', '..'):
                raise SystemExit('payload-files.txt has a non-flat name: ' + name)
            names.append(name)
    if not names:
        raise SystemExit('payload-files.txt is empty')
    return names


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', required=True, help='sealed release directory')
    parser.add_argument('--base-url', required=True, help='base URL serving that directory')
    parser.add_argument('--version', required=True, help='expected version name')
    parser.add_argument('--json', action='store_true', help='print one JSON object')
    args = parser.parse_args()

    root = os.path.abspath(args.root)
    for name in (DOCUMENT, SIDECAR, PAYLOAD_LIST):
        if not os.path.isfile(os.path.join(root, name)):
            raise SystemExit('missing ' + name + ' in ' + root)

    content = read_payload_list(root)
    base = args.base_url.rstrip('/')
    document_url = base + '/' + DOCUMENT
    env = {
        'RUNECLR_EXPECTED_VERSION': args.version,
        'RUNECLR_DELIVERY_MODE': 'http',
        'RUNECLR_DELIVERY_DOCUMENT_URL': document_url,
        'RUNECLR_DELIVERY_CONTENT_BASE': base + '/',
        'RUNECLR_DELIVERY_CONTENT': ','.join(content),
    }
    mapping = [{'file': name, 'url': base + '/' + name} for name in content]
    mapping.append({'file': SIDECAR, 'url': base + '/' + SIDECAR})
    mapping.append({'file': PAYLOAD_LIST, 'url': base + '/' + PAYLOAD_LIST})

    if args.json:
        print(json.dumps({'root': root, 'version': args.version, 'environment': env,
                          'urls': mapping}, indent=1))
        return 0

    print('release root : ' + root)
    print('serve with   : python3 -m http.server 8099 --directory ' + os.path.dirname(root))
    print('document     : ' + document_url)
    print('content files:')
    for item in mapping:
        print('  ' + item['file'] + '  ->  ' + item['url'])
    print('device env   : ' + json.dumps(env, separators=(',', ':')))
    print('launch args  : --delivery --payload ' + args.version + '-delivery-1 --nonce <owner nonce>')
    return 0


if __name__ == '__main__':
    sys.exit(main())