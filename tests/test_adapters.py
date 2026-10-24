from __future__ import annotations

import json
from contextlib import contextmanager

import httpx
import pytest

from app.drivers import TinyFishDriver
from guard.contract_parser import _draft_schema, _openai_json
from guard.models import Cart
from guard.scenarios import CONTRACT, SCENARIOS


def test_openai_reads_real_responses_output_array(monkeypatch):
    @contextmanager
    def respond(request, timeout):
        assert request.full_url == "https://api.openai.com/v1/responses"
        payload = json.loads(request.data)
        assert payload["text"]["format"]["strict"] is True
        assert "tools" not in payload  # The draft LLM has no action tools.
        class Body:
            def read(self):
                return json.dumps({
                    "status": "completed", "output": [{"type": "message", "content": [
                        {"type": "output_text", "text": CONTRACT.model_dump_json()},
                    ]}],
                }).encode()
        yield Body()
    monkeypatch.setattr("guard.contract_parser.urlopen", respond)
    assert _openai_json("One ticket", "test-not-a-real-key") == CONTRACT.model_dump()


@pytest.mark.parametrize("body", [
    {"status": "incomplete", "output": []},
    {"status": "failed", "output": []},
    {"status": "completed", "output": [{"type": "message", "content": [{"type": "refusal", "refusal": "No"}]}]},
])
def test_openai_incomplete_and_refused_drafts_fail(monkeypatch, body):
    @contextmanager
    def respond(*args, **kwargs):
        class Body:
            def read(self):
                return json.dumps(body).encode()
        yield Body()
    monkeypatch.setattr("guard.contract_parser.urlopen", respond)
    with pytest.raises(ValueError):
        _openai_json("One ticket", "test-not-a-real-key")


def test_draft_schema_uses_integer_money_and_required_nullable_fields():
    schema = _draft_schema()
    assert schema["properties"]["max_total"]["type"] == "integer"
    for obj in [schema, *schema["$defs"].values()]:
        if obj.get("type") == "object":
            assert set(obj["required"]) == set(obj["properties"])
            assert obj["additionalProperties"] is False


def test_tinyfish_streams_public_site_stage_without_commit(monkeypatch):
    expected = SCENARIOS["s2"][0].model_dump()
    calls = []
    original_client = httpx.Client
    def handler(request):
        payload = json.loads(request.content)
        calls.append(payload)
        assert str(request.url) == "https://agent.tinyfish.ai/v1/automation/run-sse"
        assert request.headers["X-API-Key"] == "test-not-a-real-key"
        event = {"type": "COMPLETE", "status": "COMPLETED", "resultJson": expected}
        stream = ": keepalive\n\ndata: " + json.dumps({"type": "PROGRESS"}) + "\n\ndata: " + json.dumps(event) + "\n\n"
        return httpx.Response(200, text=stream)
    monkeypatch.setattr("app.drivers.httpx.Client", lambda **kwargs: original_client(transport=httpx.MockTransport(handler), **kwargs))
    driver = TinyFishDriver(api_key="test-not-a-real-key")
    staged = driver.stage(CONTRACT, "s2")
    assert staged == Cart.model_validate(expected)
    assert calls[0]["url"] == "https://demo-booking-tau.vercel.app/index.html?scenario=s2"
    assert "NEVER press Confirm" in calls[0]["goal"]
    assert len(calls) == 1


@pytest.mark.parametrize("event", [
    {"type": "COMPLETE", "status": "FAILED", "resultJson": {}},
    {"type": "COMPLETE", "status": "COMPLETED", "resultJson": []},
    {"type": "ERROR"}, {"type": "FAILED"},
])
def test_tinyfish_terminal_failures_do_not_return_data(event):
    with pytest.raises((RuntimeError, ValueError)):
        TinyFishDriver._completed(event)


def test_tinyfish_missing_terminal_event_fails(monkeypatch):
    original_client = httpx.Client
    transport = httpx.MockTransport(lambda request: httpx.Response(200, text='data: {"type":"PROGRESS"}\n\n'))
    monkeypatch.setattr("app.drivers.httpx.Client", lambda **kwargs: original_client(transport=transport, **kwargs))
    with pytest.raises(RuntimeError, match="completed"):
        TinyFishDriver(api_key="test-not-a-real-key").stage(CONTRACT, "s1")
