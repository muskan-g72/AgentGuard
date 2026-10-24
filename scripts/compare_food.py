"""Print the synthetic read-only food comparison. Never stage or place an order."""

import argparse
import json

from app.food_catalog import compare_food_fixtures


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--priority", choices=("price", "taste"), default="price")
    parser.add_argument("--base-url", default="https://food-demo.example")
    args = parser.parse_args()
    report = compare_food_fixtures({"priority": args.priority}, base_url=args.base_url)
    print(json.dumps({"synthetic": True, "taste_note": "A rating/count proxy, not ground truth.",
                      **report.model_dump(mode="json")}, indent=2))


if __name__ == "__main__":
    main()
