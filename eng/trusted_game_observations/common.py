"""Small shared helpers with no import-time side effects."""

import hashlib
import json
import os
from pathlib import Path


class ObservationError(RuntimeError):
    """A retained evidence check failed."""


class OutputRefused(ObservationError):
    """The requested output location is not safe to create."""


def need(condition, message):
    if not condition:
        raise ObservationError(message)


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def sha256_file(path):
    try:
        return sha256_bytes(Path(path).read_bytes())
    except OSError as error:
        raise ObservationError('file-read ' + str(path) + ': ' + str(error))


def _unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        need(key not in result, 'duplicate-json-key ' + str(key))
        result[key] = value
    return result


def parse_json(data, label):
    try:
        return json.loads(data, object_pairs_hook=_unique_pairs)
    except ObservationError:
        raise
    except Exception as error:
        raise ObservationError('json ' + label + ': ' + type(error).__name__ + ': ' + str(error))


def load_json(path):
    try:
        data = Path(path).read_text(encoding='utf-8')
    except OSError as error:
        raise ObservationError('file-read ' + str(path) + ': ' + str(error))
    return parse_json(data, str(path))


def canonical_json(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False)


def normalized_path(path):
    return os.path.normcase(os.path.normpath(str(path)))


def same_path(first, second):
    return normalized_path(first) == normalized_path(second)


def is_sha256(value):
    if not isinstance(value, str) or len(value) != 64:
        return False
    return all(character in '0123456789abcdefABCDEF' for character in value)
