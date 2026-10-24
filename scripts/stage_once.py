"""Explicitly labelled replay/live staging only; never issues an approval/order."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
from app.staging import stage_cart_evidence, StagingError
from app.tinyfish_client import DEMO_URL
from guard.checker import check
from guard.contract_parser import DEMO_CONTRACT
from guard.models import Contract


def main():
    load_dotenv(ROOT / '.env')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('cart_url', nargs='?')
    parser.add_argument('--mode', choices=['replay', 'live'], default='replay' if os.getenv('REPLAY') == '1' else 'live')
    parser.add_argument('--scenario', default='s2')
    parser.add_argument('--contract', type=Path)
    parser.add_argument('--expected-release', help='Require the deployed content release from prepare_deployment.py')
    parser.add_argument('--review-demo', action='store_true', help='Explicitly review the printed fixed demo contract for this staging-only command')
    args = parser.parse_args()
    if args.expected_release:
        os.environ['AGENTGUARD_EXPECTED_RELEASE'] = args.expected_release
    contract = Contract.model_validate_json(args.contract.read_text(encoding='utf-8')) if args.contract else DEMO_CONTRACT
    if args.mode == 'live' and not (args.contract or args.review_demo):
        parser.error('Live staging requires --contract <reviewed.json> or --review-demo; fallback is not implicit authorization.')
    url = args.cart_url or os.getenv('DEMO_URL', DEMO_URL).rstrip('/') + '/index.html?scenario=' + args.scenario
    print(json.dumps({'mode': 'fixture_replay' if args.mode == 'replay' else 'live_agent',
                      'reviewed_staging_contract': contract.model_dump(mode='json'),
                      'note': 'Staging only: no approval, confirmation or order is created.'}, indent=2), flush=True)
    try:
        evidence = stage_cart_evidence(url, contract, scenario=args.scenario, max_attempts=1, replay=args.mode == 'replay')
        decision = check(contract, evidence.cart)
        result = {'mode': evidence.mode, 'cart': evidence.cart.model_dump(mode='json'),
                  'staged_url': evidence.staged_url, 'decision': decision.model_dump(mode='json'), 'approval': None}
        print(json.dumps(result, indent=2))
    except StagingError as error:
        print(json.dumps({'mode': args.mode, 'status': 'failed', 'error': str(error), 'approval': None}), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
