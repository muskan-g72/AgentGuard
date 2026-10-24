"""Commit gate for an already-approved task."""
from __future__ import annotations
import hashlib
from .tasks import audit, canonical_json, get_task, transition

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
