#!/usr/bin/env python3
"""Serve exactly one explicitly hashed experiment archive for at most 180 seconds."""
import argparse
import hashlib
import hmac
from http.server import BaseHTTPRequestHandler, HTTPServer
import ipaddress
import json
import os
from pathlib import Path
import re
import secrets
import socket
import threading
import time
import traceback

DEADLINE_SECONDS = 180
CHUNK = 1024 * 1024
TOKEN_HEADER = 'X-Experiment-Token'


def write_private(path, value):
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, 'w') as stream:
        json.dump(value, stream, indent=2)
        stream.write(chr(10))


def utc():
    return time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())


def serve(args):
    root, archive, output = args.root.resolve(), args.archive.resolve(), args.output.resolve()
    if not root.is_dir() or not archive.is_relative_to(root) or not archive.is_file():
        raise ValueError('Archive must be an existing explicitly named file within --root')
    if not re.fullmatch('[0-9a-fA-F]{64}', args.sha256):
        raise ValueError('--sha256 must be the independently verified archive SHA256')
    address = ipaddress.ip_address(args.bind)
    if address.version != 4 or str(address) not in ('172.26.202.95', '127.0.0.1'):
        raise ValueError('--bind must explicitly be 172.26.202.95 or 127.0.0.1')
    if output == root or archive.is_relative_to(output):
        raise ValueError('--output must be a fresh directory separate from the archive')
    output.mkdir(parents=True, mode=0o700, exist_ok=False)
    os.chmod(output, 0o700)
    expected = args.sha256.lower()
    result = {'success': False, 'archive': str(archive), 'expectedSha256': expected,
              'bind': str(address), 'startedUtc': utc(), 'deadlineSeconds': DEADLINE_SECONDS,
              'servedBytes': 0, 'successfulGets': 0, 'failedRequests': 0,
              'persistentService': False}
    server = None
    stream = None
    deadline_timer = None
    try:
        stream = archive.open('rb')
        size = os.fstat(stream.fileno()).st_size
        digest = hashlib.sha256()
        for block in iter(lambda: stream.read(CHUNK), b''):
            digest.update(block)
        if digest.hexdigest() != expected:
            raise ValueError('Actual archive SHA256 differs from the supplied verified hash')
        stream.seek(0)
        result['archiveSize'] = size
        token = secrets.token_hex(24)
        expires = time.monotonic() + DEADLINE_SECONDS
        failed = []
        active = {'connection': None}

        def expire_connection():
            connection = active['connection']
            if connection is not None:
                try:
                    connection.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass

        class Handler(BaseHTTPRequestHandler):
            protocol_version = 'HTTP/1.0'
            server_version = 'RuneCLRArtifactTransfer'
            sys_version = ''

            def setup(self):
                super().setup()
                active['connection'] = self.connection
                self.connection.settimeout(max(0.1, min(10, expires - time.monotonic())))

            def finish(self):
                try:
                    super().finish()
                finally:
                    active['connection'] = None

            def log_message(self, format, *values):
                # No default request/header logging; the private token must not enter logs.
                pass

            def do_HEAD(self):
                result['failedRequests'] += 1
                self.send_error(405, 'Only one authenticated GET is supported')

            def do_GET(self):
                if self.path != '/archive':
                    result['failedRequests'] += 1
                    self.send_error(404)
                    return
                supplied = self.headers.get_all(TOKEN_HEADER, [])
                if len(supplied) != 1 or not hmac.compare_digest(supplied[0].encode('utf-8'), token.encode('ascii')):
                    result['failedRequests'] += 1
                    self.send_error(403)
                    return
                if time.monotonic() >= expires or result['successfulGets']:
                    self.send_error(410)
                    return
                transferred, digest = 0, hashlib.sha256()
                try:
                    stream.seek(0)
                    self.send_response(200)
                    self.send_header('Content-Type', 'application/octet-stream')
                    self.send_header('Content-Length', str(size))
                    self.send_header('Cache-Control', 'no-store')
                    self.send_header('Connection', 'close')
                    self.end_headers()
                    while transferred < size:
                        remaining = expires - time.monotonic()
                        if remaining <= 0:
                            raise TimeoutError('Transfer deadline reached')
                        self.connection.settimeout(min(10, remaining))
                        block = stream.read(min(CHUNK, size - transferred))
                        if not block:
                            raise IOError('Archive length changed during transfer')
                        self.wfile.write(block)
                        digest.update(block)
                        transferred += len(block)
                    self.wfile.flush()
                    if digest.hexdigest() != expected:
                        raise IOError('Archive bytes changed during transfer')
                    result.update(success=True, servedBytes=transferred, servedSha256=digest.hexdigest(),
                                  successfulGets=1)
                except Exception:
                    result['failedRequests'] += 1
                    result['lastFailedTransferBytes'] = transferred
                    failed.append({'error': traceback.format_exc(), 'transferredBytes': transferred})
                finally:
                    self.close_connection = True

        class SingleArchiveServer(HTTPServer):
            allow_reuse_address = False

            def handle_error(self, request, client_address):
                result['failedRequests'] += 1
                failed.append({'error': traceback.format_exc(), 'phase': 'request'})

        server = SingleArchiveServer((str(address), 0), Handler)
        server.timeout = 1
        deadline_timer = threading.Timer(max(0, expires - time.monotonic()), expire_connection)
        deadline_timer.daemon = True
        deadline_timer.start()
        port = server.server_address[1]
        result['port'] = port
        write_private(output / 'request.json', {'url': 'http://' + str(address) + ':' + str(port) + '/archive',
                      'header': TOKEN_HEADER, 'token': token, 'sha256': expected, 'size': size,
                      'archive': str(archive), 'deadlineSeconds': DEADLINE_SECONDS,
                      'startedUtc': result['startedUtc'], 'persistentService': False})
        while not result['success'] and time.monotonic() < expires:
            server.handle_request()
        if not result['success']:
            result['error'] = 'No complete authenticated GET before deadline'
        if failed:
            write_private(output / 'failed-requests.json', failed)
    except Exception:
        result['error'] = traceback.format_exc()
    finally:
        if deadline_timer is not None:
            deadline_timer.cancel()
        if server is not None:
            server.server_close()
        if stream is not None:
            stream.close()
        result['endedUtc'] = utc()
        write_private(output / 'results.json', result)
    print(json.dumps(result, indent=2), flush=True)
    return 0 if result['success'] else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('root', 'archive', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--sha256', required=True)
    parser.add_argument('--bind', required=True, help='Explicit 172.26.202.95 or 127.0.0.1; never all interfaces')
    return serve(parser.parse_args())


if __name__ == '__main__':
    raise SystemExit(main())
