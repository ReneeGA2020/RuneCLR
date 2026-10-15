"""Full file inventories for the isolated Android derived-ledger build."""
import hashlib
import json
import os
from pathlib import Path


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def inventory(root):
    root = Path(root).resolve()
    if not root.is_dir():
        raise RuntimeError('Inventory root missing: ' + str(root))
    rows, cached = {}, {}
    # Directory symlinks are recorded without traversal, including SDK cycles.
    for directory, folders, files in os.walk(root, followlinks=False):
        for name in sorted(folders + files):
            path = Path(directory) / name
            relative = path.relative_to(root).as_posix()
            if path.is_symlink():
                row = {'kind': 'symlink', 'target': os.readlink(path)}
                if path.is_file():
                    resolved = str(path.resolve())
                    cached.setdefault(resolved, None)
                    if cached[resolved] is None:
                        cached[resolved] = sha(path)
                    row.update(size=path.stat().st_size, sha256=cached[resolved])
                elif not path.is_dir():
                    raise RuntimeError('Broken inventory symlink: ' + str(path))
                rows[relative] = row
            elif path.is_file():
                resolved = str(path.resolve())
                if resolved not in cached:
                    cached[resolved] = sha(path)
                rows[relative] = {'kind': 'file', 'size': path.stat().st_size,
                                  'sha256': cached[resolved]}
    if not rows:
        raise RuntimeError('Empty file inventory: ' + str(root))
    return dict(sorted(rows.items()))


def resolved_packages(source):
    assets, packages = {}, {}
    paths = sorted((Path(source) / 'artifacts/obj').rglob('project.assets.json'))
    if not paths:
        raise RuntimeError('No generated restore assets for dependency binding')
    for path in paths:
        data = json.loads(path.read_text())
        assets[str(path)] = {'size': path.stat().st_size, 'sha256': sha(path)}
        for library in data.get('libraries', {}).values():
            if library.get('type') != 'package':
                continue
            relative = library['path']
            if Path(relative).is_absolute() or '..' in Path(relative).parts:
                raise RuntimeError('Invalid resolved package path: ' + relative)
            candidates = [Path(folder) / relative for folder in data['packageFolders']
                          if (Path(folder) / relative).is_dir()]
            if len(candidates) != 1:
                raise RuntimeError('Resolved package missing or ambiguous: ' + relative)
            key = str(candidates[0].resolve())
            if key not in packages:
                packages[key] = inventory(candidates[0])
    if not packages:
        raise RuntimeError('Empty resolved package inventory')
    return {'assets': assets, 'packages': packages}


def require_unchanged(root, expected):
    if not expected or inventory(root) != expected:
        raise RuntimeError('Full dependency inventory changed: ' + str(root))
