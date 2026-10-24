"""Visible or headless local demo; --review-demo explicitly authorizes preset instructions."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import httpx
from dotenv import load_dotenv
from app.store import Store
from app.workflow import run_task
from guard.contract_parser import DEMO_CONTRACT


def main():
    load_dotenv(ROOT / '.env')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url', default=os.getenv('DEMO_LOCAL_URL', 'http://127.0.0.1:8001'))
    parser.add_argument('--db', type=Path, default=Path(os.getenv('AGENTGUARD_DB', str(ROOT / 'data' / 'workflow.db'))))
    parser.add_argument('--scenario', choices=['s1','s2','s3','s4','s5','s6'], default='s2')
    parser.add_argument('--mode', choices=['local','replay','live'], default='local')
    parser.add_argument('--headed', action='store_true')
    parser.add_argument('--confirm', action='store_true', help='Explicitly submit a simulated order only after ALLOW')
    parser.add_argument('--review-demo', action='store_true')
    args = parser.parse_args()
    if not args.review_demo:
        parser.error('Review the instructions in the website, or explicitly select --review-demo for the printed preset.')
    print('Explicitly reviewed demo contract (all three preferences: do not care):', flush=True)
    print(DEMO_CONTRACT.model_dump_json(indent=2), flush=True)
    os.environ['DEMO_LOCAL_URL'] = args.base_url.rstrip('/')
    with httpx.Client(base_url=args.base_url, timeout=30, trust_env=False) as client:
        response = client.post('/tasks', json={'sentence': 'Use the explicitly reviewed demo contract.',
                               'scenario': args.scenario, 'draft_contract': DEMO_CONTRACT.model_dump(mode='json')})
        response.raise_for_status()
        task = response.json()
        client.post('/tasks/' + task['task_id'] + '/answers', json={'answers': {q['key']: "don't care" for q in task['questions']}}).raise_for_status()
        client.post('/tasks/' + task['task_id'] + '/confirm', json={}).raise_for_status()
    result = run_task(Store(args.db), task['task_id'], args.mode, confirm=args.confirm, headed=args.headed)
    print(json.dumps(result, indent=2))
    return 1 if result['status'] == 'failed' else 0


if __name__ == '__main__':
    raise SystemExit(main())
