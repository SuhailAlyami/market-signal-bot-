"""One local command: read-only SPX acquisition, integrity checks, frozen study."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

from collect_spx_sessions import collect
from evaluate_spx_sessions import run_capture


def run(output_root, port=4001, client_id=20331025):
    root = Path(output_root)
    root.mkdir(parents=True, exist_ok=False)
    capture = root / 'capture'
    report_path = root / 'study.json'
    manifest = collect('2026-10-21', 20, capture, port, client_id)
    if manifest.get('data_complete') is not True:
        result = dict(readiness='NOT_READY', accepted=False,
                      reason='acquisition_failed_or_incomplete',
                      capture_failure=manifest.get('failure'),
                      holdout_opened=False, notifications_enabled=False, orders_enabled=False)
        with report_path.open('x', encoding='utf-8') as stream:
            json.dump(result, stream, indent=2, allow_nan=False)
            stream.write('\n')
    else:
        # One persistent registry across all timestamped run directories.
        result = run_capture(capture, report_path)
    print(json.dumps(dict(result= str(report_path), **{key: result.get(key) for key in
                     ('readiness', 'reason', 'model_selected', 'holdout_opened')})), flush=True)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', help='New run directory; defaults to a timestamped local path')
    parser.add_argument('--port', type=int, default=4001)
    parser.add_argument('--client-id', type=int, default=20331025)
    args = parser.parse_args()
    output = args.output or str(Path('.hunter-state') / ('spx-study-' +
                               datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')))
    result = run(output, args.port, args.client_id)
    raise SystemExit(0 if result['accepted'] else 2)


if __name__ == '__main__':
    main()
