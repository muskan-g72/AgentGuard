"""Testable browser-step interface around TinyFish."""
from __future__ import annotations

from typing import Protocol

from guard.models import Cart, Contract
from .staging import StagingError, _parse, stage_cart_details
from .tinyfish_client import run_agent


class BrowserError(RuntimeError): pass
class Browser(Protocol):
    def stage_cart(self, url: str, contract: Contract) -> Cart: ...
    def fix_cart(self, url: str, remove_item_ids: list[str]) -> Cart: ...
    def read_cart(self, url: str) -> Cart: ...
    def commit_order(self, url: str) -> dict: ...


class TinyFishBrowser:
    def stage_cart(self, url: str, contract: Contract) -> Cart:
        return stage_cart_details(url, contract)[0]
    def _cart(self, url: str, goal: str) -> Cart:
        for _ in range(2):
            try: return _parse(run_agent(url, goal))[0]
            except Exception: pass
        raise BrowserError("TinyFish returned malformed cart JSON twice.")
    def fix_cart(self, url: str, remove_item_ids: list[str]) -> Cart:
        return self._cart(url, f"Remove only these cart item ids: {remove_item_ids}. Do not confirm or pay. Return cart JSON.")
    def read_cart(self, url: str) -> Cart:
        return self._cart(
            url,
            "Read the current checkout cart and return only its cart JSON. "
            "Do not click Confirm, Pay, Place order, Submit, or any equivalent final-action button.",
        )
    def commit_order(self, url: str) -> dict:
        for _ in range(2):
            try:
                result = run_agent(url, "Confirm the simulated order and return JSON with order_id and integer total.")["result"]
                if isinstance(result, dict) and isinstance(result.get("order_id"), str) and isinstance(result.get("total"), int): return result
            except Exception: pass
        raise BrowserError("TinyFish returned malformed order JSON twice.")


class FakeBrowser:
    def __init__(self, *, carts: list[Cart] = [], read_carts: list[Cart] = [], orders: list[dict] = []):
        self.carts, self.read_carts, self.orders = list(carts), list(read_carts), list(orders)
        self.commit_calls, self.stage_calls, self.fix_calls, self.read_calls = 0, 0, 0, 0
        self.last_staged_cart = None
    def stage_cart(self, url: str, contract: Contract) -> Cart:
        self.stage_calls += 1
        self.last_staged_cart = self.carts.pop(0)
        return self.last_staged_cart
    def fix_cart(self, url: str, remove_item_ids: list[str]) -> Cart: self.fix_calls += 1; return self.carts[0]
    def read_cart(self, url: str) -> Cart:
        self.read_calls += 1
        if self.read_carts:
            return self.read_carts.pop(0)
        if self.last_staged_cart is None:
            raise BrowserError("No scripted live cart is available.")
        return self.last_staged_cart
    def commit_order(self, url: str) -> dict:
        self.commit_calls += 1
        return self.orders.pop(0)
