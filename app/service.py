"""Task lifecycle, deterministic checking, bounded repair, and the commit gate."""

from __future__ import annotations

import hashlib
import uuid

from fastapi import HTTPException

from guard.checker import check
from guard.contract_parser import parse_contract, questions_for
from guard.models import Cart, Contract, Decision, OrderRequest
from guard.request_check import canonical_json, cart_hash, request_check

from .drivers import PageUnverified
from .store import Store


def fingerprint(value: dict) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


class TaskService:
    def __init__(self, store: Store, driver):
        self.store = store
        self.driver = driver

    def create(self, sentence: str, scenario: str, guard_enabled: bool) -> dict:
        contract = parse_contract(sentence)
        questions = [question.model_dump(mode="json") for question in questions_for(contract)]
        task = {
            "task_id": uuid.uuid4().hex, "sentence": sentence, "scenario": scenario,
            "guard_enabled": guard_enabled, "draft_contract": contract.model_dump(mode="json"),
            "contract": None, "questions": questions,
            "status": "awaiting_answers" if questions else "awaiting_confirmation",
            "decision_history": [], "cart": None, "allowed_cart_hash": None,
            "allowed_contract_hash": None, "order_request": None, "final": None,
            "signature": None, "running": False,
        }
        self.store.create(task)
        return {key: task[key] for key in ("task_id", "draft_contract", "questions")}

    def answers(self, task_id: str, answers: dict[str, str]) -> dict:
        def action(task, append):
            expected = {question["key"] for question in task["questions"]}
            if task["status"] != "awaiting_answers" or set(answers) != expected:
                append("answers_rejected", {"status": task["status"], "keys": sorted(answers)})
                return None
            draft = Contract.model_validate(task["draft_contract"]).model_dump(mode="json")
            mapping = {"yes": True, "no": False, "don't care": None}
            draft["requirements"].update({key: mapping[value] for key, value in answers.items()})
            task["draft_contract"] = Contract.model_validate(draft).model_dump(mode="json")
            append("answers_recorded", {"answers": answers})
            self.store.move(task, append, "awaiting_confirmation")
            return task["draft_contract"]
        contract = self.store.mutate(task_id, action)
        if contract is None:
            raise HTTPException(409, "Answer every pending question while awaiting_answers")
        return {"contract": contract}

    def confirm(self, task_id: str, contract: Contract | None) -> dict:
        def action(task, append):
            if task["status"] != "awaiting_confirmation":
                append("confirmation_rejected", {"status": task["status"]})
                return False
            confirmed = contract or Contract.model_validate(task["draft_contract"])
            # Fallback provenance cannot be erased by a confirmation edit.
            value = confirmed.model_dump(mode="json")
            value["source"] = task["draft_contract"]["source"]
            task["contract"] = Contract.model_validate(value).model_dump(mode="json")
            append("contract_confirmed", {"contract": task["contract"]})
            return self.store.move(task, append, "staging")
        if not self.store.mutate(task_id, action):
            raise HTTPException(409, "The task must await confirmation")
        return {"status": "staging"}

    def _decision(self, task_id: str, cart: Cart, decision: Decision, phase: str):
        def action(task, append):
            task["cart"] = cart.model_dump(mode="json")
            entry = {"phase": phase, "cart_hash": cart_hash(cart), **decision.model_dump(mode="json")}
            task["decision_history"].append(entry)
            task["allowed_cart_hash"] = entry["cart_hash"] if decision.result == "allow" else None
            task["allowed_contract_hash"] = fingerprint(task["contract"]) if decision.result == "allow" else None
            append("decision", entry)
        self.store.mutate(task_id, action)

    def _claim(self, task_id: str):
        def action(task, append):
            if task["status"] != "staging" or task["running"] or not task["contract"]:
                append("run_rejected", {"status": task["status"], "running": task["running"]})
                return False
            task["running"] = True
            append("run_started", {"replay": self.driver.replay})
            return True
        if not self.store.mutate(task_id, action):
            raise HTTPException(409, "Confirm the task first; a task can run only once")

    def run(self, task_id: str) -> dict:
        self._claim(task_id)
        try:
            if not self.store.key:
                raise RuntimeError("RECEIPT_KEY is required")
            task = self.store.get(task_id, events=False)
            contract = Contract.model_validate(task["contract"])
            cart = Cart.model_validate(self.driver.stage(contract, task["scenario"]))
            self.store.audit(task_id, "cart_staged", {"cart": cart.model_dump(mode="json")})
            if not self.store.transition(task_id, "checking"):
                raise HTTPException(409, "Invalid checking transition")
            repaired = False
            while True:
                decision = check(contract, cart)
                self._decision(task_id, cart, decision, "cart")
                if decision.result == "allow":
                    try:
                        allowed_hash = self.store.get(task_id, events=False)["allowed_cart_hash"]
                        outgoing = OrderRequest.model_validate(self.driver.prepare_request(cart.model_copy(deep=True)))
                        decision = request_check(contract, cart, outgoing, allowed_hash)
                    except PageUnverified:
                        decision = Decision(result="block", reasons=["The live outgoing order request cannot be verified."], flags=["page_unverified"])
                        outgoing = None
                    self._decision(task_id, cart, decision, "request")
                    if decision.result == "allow":
                        def authorize(current, append):
                            current["order_request"] = outgoing.model_dump(mode="json")
                            append("request_verified", {"order_request": current["order_request"]})
                            return self.store.move(current, append, "allowed")
                        if not self.store.mutate(task_id, authorize):
                            raise HTTPException(409, "Invalid allow transition")
                        self.commit(task_id)
                        break
                if not self.store.transition(task_id, "blocked"):
                    raise HTTPException(409, "Invalid blocked transition")
                removable = set(decision.remove_item_ids)
                # Fees are mandatory in the demo; only optional insurance and meal
                # have removal controls. Repair at most once, then re-check.
                can_fix = (
                    task["guard_enabled"] and not repaired and bool(removable)
                    and all(item.type in ("insurance", "meal") for item in cart.items if item.id in removable)
                )
                if not can_fix:
                    break
                if not self.store.transition(task_id, "fixing"):
                    raise HTTPException(409, "Invalid fixing transition")
                cart = Cart.model_validate(self.driver.fix(contract, task["scenario"], cart, sorted(removable)))
                self.store.audit(task_id, "cart_fixed", {"cart": cart.model_dump(mode="json"), "remove_item_ids": sorted(removable)})
                repaired = True
                if not self.store.transition(task_id, "checking"):
                    raise HTTPException(409, "Invalid re-check transition")
        except HTTPException:
            raise
        except Exception as exc:
            # Do not leak API keys or vendor response bodies into the audit log.
            def fail(current, append):
                append("execution_failed", {"error_type": type(exc).__name__})
                if current["status"] != "failed":
                    self.store.move(current, append, "failed")
            self.store.mutate(task_id, fail)
        finally:
            self.store.mutate(task_id, lambda current, append: current.update(running=False))
        return self.store.get(task_id)

    def commit(self, task_id: str) -> dict:
        """Atomically consume an allow before invoking any commit transport."""
        def gate(task, append):
            latest = task["decision_history"][-1] if task["decision_history"] else {}
            reasons = []
            if task["status"] != "allowed":
                reasons.append("status")
            if latest.get("result") != "allow":
                reasons.append("decision")
            try:
                if not task["allowed_cart_hash"] or cart_hash(task["cart"]) != task["allowed_cart_hash"]:
                    reasons.append("cart_hash")
                if fingerprint(task["contract"]) != task["allowed_contract_hash"]:
                    reasons.append("contract_hash")
                decision = request_check(task["contract"], task["cart"], task["order_request"], task["allowed_cart_hash"])
                if decision.result != "allow":
                    reasons.append("order_request")
            except (ValueError, TypeError):
                reasons.append("invalid_data")
            if not self.store.key:
                reasons.append("receipt_key")
            if reasons:
                append("commit_rejected", {"reasons": reasons})
                return None
            outgoing = OrderRequest.model_validate(task["order_request"])
            if not self.store.move(task, append, "committing"):
                return None
            append("commit_started", {"cart_hash": task["allowed_cart_hash"], "order_request": outgoing.model_dump(mode="json")})
            return outgoing
        outgoing = self.store.mutate(task_id, gate)
        if outgoing is None:
            raise HTTPException(409, "Commit gate rejected the task; see audit events")
        try:
            final = self.driver.commit(outgoing)
            if (not isinstance(final, dict) or not isinstance(final.get("order_id"), str)
                    or not final["order_id"] or type(final.get("total")) is not int
                    or final["total"] != outgoing.total):
                raise ValueError("Invalid merchant confirmation")
            final = {"order_id": final["order_id"], "total": final["total"]}
            def finish(task, append):
                task["final"] = final
                append("order_committed", {"final": final})
                return self.store.move(task, append, "done")
            if not self.store.mutate(task_id, finish):
                raise HTTPException(409, "Invalid done transition")
            return final
        except Exception:
            self.store.audit(task_id, "commit_failed", {"message": "The simulated order did not complete"})
            self.store.transition(task_id, "failed")
            raise
