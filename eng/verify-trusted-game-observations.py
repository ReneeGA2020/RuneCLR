#!/usr/bin/env python3
"""Verify one retained trusted-game observation run offline.

The CLI derives its expected call set from the actual commands, images, maps,
PE metadata, signed documents, receipts and raw logs in --run-root on every
invocation. It does not accept an external expected file and does not execute
the product, build, crossgen, signing, Host, Publisher, private CLR or a device.

Usage:
    python -B eng/verify-trusted-game-observations.py \
        --run-root <retained-run> --output <new-directory>

Exit codes:
    0  validation passed and a new report was written
    1  output already exists, is the run root, or is inside the run root
    2  validation failed or input/report I/O failed; no new report is written
"""

import argparse
import json
from pathlib import Path
import sys


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from trusted_game_observations.common import ObservationError, OutputRefused
from trusted_game_observations.verify import verify_run


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--run-root', required=True, type=Path,
                        help='retained run directory containing commands/images/maps/observations')
    parser.add_argument('--output', required=True, type=Path,
                        help='new directory that will receive report.json and report.sha256')
    args = parser.parse_args(argv)
    try:
        summary = verify_run(args.run_root, args.output)
    except OutputRefused as error:
        print('ERROR: ' + str(error), file=sys.stderr)
        return 1
    except ObservationError as error:
        print('ERROR: ' + str(error), file=sys.stderr)
        return 2
    except Exception as error:
        print('ERROR: ' + type(error).__name__ + ': ' + str(error), file=sys.stderr)
        return 2
    print(json.dumps(summary, indent=1))
    return 0


if __name__ == '__main__':
    sys.exit(main())
