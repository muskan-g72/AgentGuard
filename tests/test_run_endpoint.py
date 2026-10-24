from fastapi.testclient import TestClient
import app.main as main
from app.browser import FakeBrowser
from app.tasks import get_task, task_events
from guard.scenarios import SCENARIOS

def make(client, confirm=False):
 t=client.post('/tasks',json={'sentence':'x','scenario':'s1','guard_enabled':False}).json()['task_id']
 if confirm: client.post(f'/tasks/{t}/confirm',json={})
 return t

def test_unconfirmed_run_refused(monkeypatch):
 b=FakeBrowser(); monkeypatch.setattr(main,'BROWSER_FACTORY',lambda:b); c=TestClient(main.app); t=make(c); r=c.post(f'/tasks/{t}/run'); assert r.status_code==409 and b.stage_calls==0 and get_task(t)['status']=='awaiting_confirmation' and any(e['type']=='run_rejected' for e in task_events(t))

def test_confirmed_run_schedules_background(monkeypatch):
 b=FakeBrowser(carts=[SCENARIOS['s1'][0]],orders=[{'order_id':'o','total':1000}]); monkeypatch.setattr(main,'BROWSER_FACTORY',lambda:b); c=TestClient(main.app); t=make(c,True); r=c.post(f'/tasks/{t}/run'); assert r.status_code==202 and b.stage_calls==1

def test_lookalike_origin_rejected(monkeypatch):
 monkeypatch.setenv('DEMO_SITE_BASE','https://demo-booking-tau.vercel.app.evil.com'); b=FakeBrowser(); monkeypatch.setattr(main,'BROWSER_FACTORY',lambda:b); c=TestClient(main.app); t=make(c,True); assert c.post(f'/tasks/{t}/run').status_code==400 and get_task(t)['status']=='failed' and b.stage_calls==0 and 'run_failed' in [e['type'] for e in task_events(t)]

def test_localhost_replay_rule(monkeypatch):
 monkeypatch.setenv('DEMO_SITE_BASE','http://localhost:8000'); monkeypatch.delenv('REPLAY',raising=False); b=FakeBrowser(); monkeypatch.setattr(main,'BROWSER_FACTORY',lambda:b); c=TestClient(main.app); t=make(c,True); assert c.post(f'/tasks/{t}/run').status_code==400 and get_task(t)['status']=='failed' and b.stage_calls==0
 monkeypatch.setenv('REPLAY','1'); b=FakeBrowser(carts=[SCENARIOS['s1'][0]],orders=[{'order_id':'o','total':1000}]); monkeypatch.setattr(main,'BROWSER_FACTORY',lambda:b); t=make(c,True); assert c.post(f'/tasks/{t}/run').status_code==202 and b.stage_calls==1

def test_rejected_origin_records_transition(monkeypatch):
 monkeypatch.setenv('DEMO_SITE_BASE','https://bad.example'); b=FakeBrowser(); monkeypatch.setattr(main,'BROWSER_FACTORY',lambda:b); c=TestClient(main.app); t=make(c,True); assert c.post(f'/tasks/{t}/run').status_code==400; assert get_task(t)['status']=='failed'; assert any(e['type']=='status_changed' and e['payload']['to']=='failed' for e in task_events(t))
