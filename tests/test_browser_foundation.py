from app.browser import FakeBrowser, TinyFishBrowser, BrowserError
from app.tasks import canonical_json, save_cart
from guard.scenarios import SCENARIOS, CONTRACT
import pytest

def test_cart_hash_changes_with_price(client=None):
    cart = SCENARIOS['s1'][0]
    assert canonical_json(cart.model_dump(mode='json')) == canonical_json(cart.model_dump(mode='json'))
    changed = cart.model_copy(deep=True); changed.items[0].price = 999
    assert canonical_json(cart.model_dump(mode='json')) != canonical_json(changed.model_dump(mode='json'))

def test_fake_browser_returns_scripted_cart():
    cart = SCENARIOS['s1'][0]
    assert FakeBrowser(carts=[cart]).stage_cart('x', CONTRACT) == cart

def test_malformed_twice_raises(monkeypatch):
    monkeypatch.setattr('app.browser.run_agent', lambda *_: {'result': {}})
    with pytest.raises(BrowserError): TinyFishBrowser().commit_order('x')
