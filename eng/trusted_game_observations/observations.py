"""JSONL observation parsing and exact gameplay/fact checks."""

import json
import re

from .common import ObservationError, need, normalized_path


def as_int(value, label):
    if isinstance(value, bool) or isinstance(value, float):
        raise ObservationError('bad-integer ' + label + ' ' + repr(value))
    if isinstance(value, int):
        return value
    try:
        return int(value, 0)
    except (TypeError, ValueError):
        raise ObservationError('bad-integer ' + label + ' ' + repr(value))


def zero_int(value, label):
    need(type(value) is int and value == 0, 'bad-zero ' + label + ' ' + repr(value))
    return value


def positive_int(value, label):
    need(type(value) is int and value > 0, 'bad-positive ' + label + ' ' + repr(value))
    return value


def _unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        need(key not in result, 'duplicate-json-key ' + str(key))
        result[key] = value
    return result


def parse_observations(text):
    records = []
    for number, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        if not line.lstrip().startswith('{'):
            raise ObservationError('malformed-line ' + str(number))
        try:
            item = json.loads(line, object_pairs_hook=_unique_pairs)
        except ObservationError:
            raise
        except Exception as error:
            raise ObservationError('malformed-json ' + str(number) + ' ' + str(error))
        need(item.get('recordType') == 'CallerObservation', 'record-type ' + str(number))
        records.append(item)
    return records


def normalized(path):
    return normalized_path(path)


def parse_signed_facts(text):
    rows = [line for line in text.splitlines() if line.startswith('SIGNED-FACTS ')]
    need(len(rows) == 1, 'signed-facts-rows ' + str(len(rows)))
    fields = {}
    for token in rows[0].split()[1:]:
        need('=' in token, 'signed-facts-token ' + token)
        key, value = token.split('=', 1)
        need(key not in fields, 'signed-facts-duplicate ' + key)
        fields[key] = value
    return fields


def expected_facts(mode, version, multiplier, source):
    return {
        'mode': mode,
        'stage': 'OK' if mode == 'stage' else 'NA',
        'stageDetail': '',
        'source': source,
        'version': version,
        'persistence': 'None',
        'persistenceDetail': '',
        'activated': 'True',
        'activatorCalls': '1',
        'expectedScoreMultiplier': str(multiplier),
        'candidateVerification': 'None',
        'candidatePlan': 'None',
        'candidateActivation': 'None',
        'recoveryVerification': 'None',
        'recoveryPlan': 'None',
        'recoveryActivation': 'None',
    }


def check_facts(fields, mode, version, multiplier, source):
    expected = expected_facts(mode, version, multiplier, source)
    need(set(fields) == set(expected),
         'facts-keys ' + repr(sorted(set(fields) ^ set(expected))))
    for key, value in expected.items():
        if fields.get(key) != value:
            raise ObservationError('facts ' + key + '=' + str(fields.get(key)) +
                                   ' expected ' + value)


def check_gameplay(text, multiplier):
    values = {1: (1, 3, 6), 2: (2, 6, 12)}[multiplier]
    expected = [
        'TRUSTED-GAME normal results=' + ','.join(map(str, values)) +
        ' score=' + str(values[2]) + ' ticks=3 multiplier=' + str(multiplier),
        'TRUSTED-GAME negative failure=CallbackFailed next=Closed score=0',
        'TRUSTED-GAME OK',
    ]
    actual = [line.strip() for line in text.splitlines()
              if line.strip().startswith('TRUSTED-GAME')]
    if actual != expected:
        raise ObservationError('gameplay-sequence ' + repr(actual))


def check_caller_line(text, leaf_path, leaf_sha):
    rows = [line for line in text.splitlines() if line.startswith('CALLERDLL ')]
    need(len(rows) == 1, 'caller-line-rows ' + str(len(rows)))
    line = rows[0]
    prefix = 'CALLERDLL '
    suffix = ' module=TrustedGame.Update'
    need(line.startswith(prefix), 'caller-line-prefix')
    need(line.endswith(suffix), 'caller-line-module')
    body = line[len(prefix):-len(suffix)]
    need(body.startswith('path='), 'caller-line-path')
    need(' module=' not in body, 'caller-line-duplicate')
    marker = ' hash='
    occurrences = body.count(marker)
    need(occurrences != 0, 'caller-line-hash')
    need(occurrences == 1, 'caller-line-duplicate')
    index = body.find(marker)
    path = body[len('path='):index]
    digest = body[index + len(marker):]
    need(path, 'caller-line-path')
    need(not any(token in path for token in (' path=', ' hash=', ' module=')),
         'caller-line-duplicate')
    need(re.fullmatch(r'[0-9a-fA-F]{64}', digest) is not None, 'caller-line-hash')
    need(normalized_path(path) == normalized_path(leaf_path), 'caller-line-leaf')
    need(digest.lower() == str(leaf_sha).lower(), 'caller-line-hash')
