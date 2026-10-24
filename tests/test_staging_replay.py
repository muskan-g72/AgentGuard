from __future__ import annotations

from app.staging import stage_cart_details
from guard.checker import check
from guard.contract_parser import DEMO_CONTRACT


def test_s2_replay_stages_and_blocks_extras(monkeypatch):
    monkeypatch.setenv("REPLAY", "1")
    cart, hidden_text = stage_cart_details(
        "http://localhost:8000/checkout.html?scenario=s2&ticket=t1&insurance=1&meal=1&fee=0",
        DEMO_CONTRACT,
    )

    assert cart.total == 1350
    assert [(item.type, item.price) for item in cart.items[1:]] == [
        ("insurance", 250),
        ("meal", 100),
    ]
    assert hidden_text == []
    decision = check(DEMO_CONTRACT, cart, hidden_text)
    assert decision.result == "block"
    assert decision.remove_item_ids == ["x1", "m1"]
