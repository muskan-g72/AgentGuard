"""Opt-in one-call LLM parser smoke. Never authorizes, stages or confirms a booking."""

import argparse
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dotenv import load_dotenv
from guard.contract_parser import parse_contract


SENTENCE = "Book two train tickets from Ludhiana to Delhi on 26 October 2026, maximum total Rs 2500, no extras. I need a confirmed seat. No refundable fare. I don't care about baggage."


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="Explicitly opt into one paid Responses API call")
    parser.add_argument("--sentence", default=SENTENCE)
    args = parser.parse_args(argv)
    if not args.live:
        print(json.dumps({"status": "not_run", "api_parse_succeeded": False,
                          "note": "Add --live to opt into one API call. No call was made."}))
        return 2
    load_dotenv(ROOT / ".env")
    if not os.getenv("OPENAI_API_KEY"):
        print(json.dumps({"status": "missing_key", "api_parse_succeeded": False, "note": "Configure OPENAI_API_KEY locally; it is never printed."}))
        return 1
    contract = parse_contract(args.sentence)
    parsed = contract.source == "parsed"
    print(json.dumps({"status": "api_parsed_draft" if parsed else "fallback_demo_contract",
                      "api_parse_succeeded": parsed, "model": os.getenv("GUARD_LLM_MODEL", "gpt-4.1-mini"),
                      "contract": contract.model_dump(mode="json"),
                      "note": "Draft only; human review is still required. Fallback is not a successful API parse or authorization."}, indent=2))
    return 0 if parsed else 1


if __name__ == "__main__":
    raise SystemExit(main())
