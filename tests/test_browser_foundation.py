from app.browser import FakeBrowser, TinyFishBrowser
from app.store import canonical
from guard.scenarios import SCENARIOS, CONTRACT

def test_cart_hash_changes_with_price(client=None):
    cart = SCENARIOS['s1'][0]
    assert canonical(cart.model_dump(mode='json')) == canonical(cart.model_dump(mode='json'))
    changed = cart.model_copy(deep=True); changed.items[0].price = 999
    assert canonical(cart.model_dump(mode='json')) != canonical(changed.model_dump(mode='json'))

def test_fake_browser_returns_scripted_cart():
    cart = SCENARIOS['s1'][0]
    assert FakeBrowser(carts=[cart]).stage_cart('x', CONTRACT) == cart

def test_agent_browser_has_no_direct_commit_capability():
    assert not hasattr(TinyFishBrowser(), "commit_order")
    assert not hasattr(FakeBrowser(), "commit_order")
