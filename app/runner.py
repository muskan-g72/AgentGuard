"""Commit gate for an already-approved task."""
from __future__ import annotations
import hashlib
from .tasks import audit, canonical_json, get_task, transition
from .tasks import increment_fix_attempts, require_confirmed, save_cart, save_decision
from guard.models import Cart, Contract
from guard.checker import check

def commit_task(task_id: str, browser) -> bool:
    task = get_task(task_id)
    decision = task["decision"] or {}
    if task["status"] != "allowed":
        audit(task_id, "commit_refused", {"reason": "task.status is not allowed"}); return False
    if decision.get("result") != "allow":
        audit(task_id, "commit_refused", {"reason": "latest decision.result is not allow"}); return False
    digest = hashlib.sha256(canonical_json(task["cart"]).encode()).hexdigest()
    if digest != task["cart_hash"]:
        audit(task_id, "commit_refused", {"reason": "stored cart hash does not match"}); return False
    transition(task_id, "committing")
    audit(task_id, "commit_started", {"cart": task["cart"], "total": task["cart"]["total"]})
    result = browser.commit_order("")
    if result.get("total") != task["cart"]["total"]:
        audit(task_id, "total_mismatch", {"approved_total": task["cart"]["total"], "confirmed_total": result.get("total")})
        transition(task_id, "failed"); return False
    audit(task_id, "commit_result", {"order_id": result.get("order_id"), "total": result["total"]})
    transition(task_id, "done"); return True

def run_task(task_id: str, browser) -> None:
    try:
        task=get_task(task_id); require_confirmed(task); contract=Contract.model_validate(task['contract']); transition(task_id,'staging')
        while True:
            audit(task_id,'stage_started',{}); cart=browser.stage_cart('',contract); save_cart(task_id,cart); audit(task_id,'cart_staged',{'cart':cart.model_dump(mode='json')});
            if get_task(task_id)['status']=='staging': transition(task_id,'checking')
            task=get_task(task_id)
            decision={'result':'allow','reasons':[],'remove_item_ids':[],'flags':['guard_disabled'],'differing_fields':[]} if not task['guard_enabled'] else check(contract,cart,cart.hidden_text).model_dump(mode='json')
            if decision['result']=='ask': decision['flags'].append('needs_user')
            save_decision(task_id,decision); audit(task_id,'check_result',{'cart':cart.model_dump(mode='json'),'decision':decision,'remove_item_ids':decision['remove_item_ids']})
            if decision['result']=='allow': transition(task_id,'allowed'); commit_task(task_id,browser); return
            transition(task_id,'blocked')
            if decision['result']=='ask': return
            if get_task(task_id)['fix_attempts'] >= 2: transition(task_id,'failed'); return
            transition(task_id,'fixing'); attempts=increment_fix_attempts(task_id); audit(task_id,'fix_started',{'remove_item_ids':decision['remove_item_ids'],'attempt':attempts}); browser.fix_cart('',decision['remove_item_ids']); audit(task_id,'fix_result',{'remove_item_ids':decision['remove_item_ids']}); transition(task_id,'checking')
    except Exception as error:
        task=get_task(task_id)
        audit(task_id,'run_failed',{'error':str(error)})
        if task['status'] not in {'failed','done'}: transition(task_id,'failed')
