from fastapi.testclient import TestClient
from app.main import app
from app.runner import run_task
from app.browser import FakeBrowser, BrowserError
from app.tasks import get_task, task_events
from guard.scenarios import SCENARIOS

def task(guard=True):
 c=TestClient(app); x=c.post('/tasks',json={'sentence':'x','scenario':'s2','guard_enabled':guard}).json()['task_id']; c.post(f'/tasks/{x}/confirm',json={}); return x
def types(t): return [e['type'] for e in task_events(t)]
def test_s2_fix_allow_commit():
 t=task(); b=FakeBrowser(carts=[SCENARIOS['s2'][0],SCENARIOS['s2-after-fix'][0]],orders=[{'order_id':'o','total':1000}]); run_task(t,b); x=get_task(t); assert (x['status'],x['fix_attempts'],x['cart']['total'])==('done',1,1000); assert (b.stage_calls,b.fix_calls,b.commit_calls)==(2,1,1); assert types(t).index('fix_started') < types(t).index('commit_result')
def test_guard_off_commits():
 t=task(False); b=FakeBrowser(carts=[SCENARIOS['s2'][0]],orders=[{'order_id':'o','total':1350}]); run_task(t,b); x=get_task(t); assert x['status']=='done' and 'guard_disabled' in x['decision']['flags']; assert b.commit_calls==1 and x['cart_hash']; assert types(t).index('check_result')<types(t).index('commit_result')
def test_ask_stops(monkeypatch):
 t=task(); b=FakeBrowser(carts=[SCENARIOS['s1'][0]]); monkeypatch.setattr('app.runner.check',lambda *a:type('D',(),{'model_dump':lambda s,mode:{'result':'ask','reasons':[],'remove_item_ids':[],'flags':[],'differing_fields':[]}})()); run_task(t,b); assert get_task(t)['status']=='blocked' and b.fix_calls==b.commit_calls==0 and 'needs_user' in get_task(t)['decision']['flags']
def test_stage_error(monkeypatch):
 t=task(); b=FakeBrowser(); monkeypatch.setattr(b,'stage_cart',lambda *a:(_ for _ in ()).throw(BrowserError('x'))); run_task(t,b); assert get_task(t)['status']=='failed' and b.commit_calls==0 and 'run_failed' in types(t)
