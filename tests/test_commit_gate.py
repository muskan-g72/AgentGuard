from fastapi.testclient import TestClient
from app.main import app
from app.tasks import get_task, save_cart, save_decision, transition, update_task, task_events
from app.browser import FakeBrowser
from app.runner import commit_task
from guard.scenarios import SCENARIOS

def prepared(result='allow'):
    c=TestClient(app); r=c.post('/tasks',json={'sentence':'x','scenario':'s1','guard_enabled':True}).json(); tid=r['task_id']; c.post(f'/tasks/{tid}/confirm',json={}); transition(tid,'staging'); transition(tid,'checking'); save_cart(tid,SCENARIOS['s1'][0]); save_decision(tid,{'result':result,'reasons':[],'remove_item_ids':[],'flags':[],'differing_fields':[]}); transition(tid,'allowed' if result=='allow' else 'blocked'); return tid
def test_block_refused():
    tid=prepared('block'); b=FakeBrowser(orders=[{'order_id':'o','total':1000}]); assert not commit_task(tid,b,'cart'); assert b.commit_calls==0
def test_changed_refused():
    tid=prepared(); update_task(tid,cart_json='{}'); b=FakeBrowser(); assert not commit_task(tid,b,'cart'); assert b.commit_calls==0
def test_status_refused():
    tid=prepared(); update_task(tid,status='blocked'); b=FakeBrowser(); assert not commit_task(tid,b,'cart'); assert b.commit_calls==0
def test_allow_commits():
    tid=prepared(); b=FakeBrowser(read_carts=[SCENARIOS['s1'][0]],orders=[{'order_id':'o','total':1000}]); assert commit_task(tid,b,'cart'); assert b.read_calls==1 and b.commit_calls==1; assert get_task(tid)['status']=='done'
def test_total_mismatch():
    tid=prepared(); b=FakeBrowser(read_carts=[SCENARIOS['s1'][0]],orders=[{'order_id':'o','total':999}]); assert not commit_task(tid,b,'cart'); assert get_task(tid)['status']=='failed'; assert any(e['type']=='total_mismatch' for e in task_events(tid))
