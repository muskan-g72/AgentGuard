"""Inspect saved simulated task/order records without exposing approval tokens."""
import argparse
import json
import httpx

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--base-url', default='http://127.0.0.1:8001')
choice = parser.add_mutually_exclusive_group(required=True)
choice.add_argument('--task-id')
choice.add_argument('--order-id')
args = parser.parse_args()
path = '/tasks/' + args.task_id if args.task_id else '/api/orders/' + args.order_id
with httpx.Client(base_url=args.base_url, timeout=15, trust_env=False) as client:
    response = client.get(path)
    response.raise_for_status()
    print(json.dumps(response.json(), indent=2))
