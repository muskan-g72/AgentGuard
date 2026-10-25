"""Print checker decisions for the complete local demo set."""

from __future__ import annotations

from .checker import check
from .scenarios import CONTRACT, SCENARIOS


def main() -> None:
    for name, (cart, hidden_text) in SCENARIOS.items():
        print(f"{name}: {check(CONTRACT, cart, hidden_text).model_dump(mode='json')}")


if __name__ == "__main__":
    main()
