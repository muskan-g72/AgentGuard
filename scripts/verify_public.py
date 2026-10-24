"""Read-only public version/protection checks; no TinyFish or LLM calls."""

import argparse
import json
from pathlib import Path
import sys
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.config import PUBLIC_ORIGIN
from app.readiness import ReadinessError, verify_readiness


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=PUBLIC_ORIGIN)
    parser.add_argument("--expected-release")
    parser.add_argument("--allow-local", action="store_true", help="Local verification only; never used by TinyFish")
    parser.add_argument("--backend-only", action="store_true", help="Verify direct backend before linking the Vercel proxy")
    args = parser.parse_args()
    if args.allow_local and urlparse(args.base_url).hostname not in {"127.0.0.1", "localhost"}:
        parser.error("--allow-local is limited to loopback origins and cannot weaken public preflight")
    try:
        print(json.dumps(verify_readiness(args.base_url, expected_release=args.expected_release,
                         require_durable=not args.allow_local, require_proxy=not (args.allow_local or args.backend_only),
                         expected_public_origin=PUBLIC_ORIGIN if args.backend_only else None), indent=2))
    except ReadinessError as error:
        print(json.dumps({"ready": False, "reason": str(error), "live_agent_executed": False}), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
