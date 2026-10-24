"""Stage and check one cart URL from the command line."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.staging import stage_cart_details  # noqa: E402
from guard.checker import check  # noqa: E402
from guard.contract_parser import DEMO_CONTRACT  # noqa: E402


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python scripts/stage_once.py <cart_url>")
    cart, hidden_text = stage_cart_details(sys.argv[1], DEMO_CONTRACT)
    decision = check(DEMO_CONTRACT, cart, hidden_text)
    print(json.dumps({"cart": cart.model_dump(mode="json"), "decision": decision.model_dump(mode="json")}, indent=2))


if __name__ == "__main__":
    main()
