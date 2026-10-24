"""Mocked HTTP protocol tests, never evidence of a successful live agent run."""

import io
import json
from urllib.error import HTTPError

import pytest

from app import tinyfish_client as client
from app import staging
from guard.contract_parser import DEMO_CONTRACT


URL = "https://demo-booking-tau.vercel.app/index.html?scenario=s2"


class Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


def stream(*events):
    return Response(b"".join(b"data: " + json.dumps(event).encode() + b"\n\n" for event in events))


@pytest.fixture
def mocked_agent(monkeypatch):
    monkeypatch.setattr(client, "preflight_live", lambda _: None)
    monkeypatch.setattr(client, "_load_key", lambda: "mock-key-never-live")
    cancelled = []
    monkeypatch.setattr(client, "_cancel", lambda run_id, _: cancelled.append(run_id))
    return cancelled


def test_sse_progress_and_documented_nonbeta_payload(monkeypatch, mocked_agent):
    calls = []
    def urlopen(request, timeout):
        calls.append((request, timeout))
        return stream({"type": "STARTED", "run_id": "run_1"}, {"type": "PROGRESS"},
                      {"type": "HEARTBEAT"}, {"type": "COMPLETE", "status": "COMPLETED", "result": {"cart": {}}})
    monkeypatch.setattr(client, "urlopen", urlopen)
    progress = []
    result = client.run_agent(URL, "stage only", progress=progress.append)
    assert result["status"] == "COMPLETED"
    assert any("PROGRESS" in text for text in progress)
    request, timeout = calls[0]
    body = json.loads(request.data)
    assert request.full_url.endswith("/run-sse")
    assert body["agent_config"] == {"max_duration_seconds": 120}
    assert "capture_config" not in body and "browser_profile" not in body
    assert body["output_schema"]["properties"]["cart"]["properties"]["total"] == {"type": "integer", "nullable": True}
    assert timeout <= 20
    assert mocked_agent == []


@pytest.mark.parametrize("events", [
    [{"type": "STARTED", "run_id": "run_1"}],
    [{"type": "COMPLETE", "status": "FAILED", "error": {"message": "private key must not appear"}}],
    [{"type": "COMPLETE", "status": "COMPLETED", "result": None}],
])
def test_partial_or_failed_stream_never_returns_cart(monkeypatch, mocked_agent, events):
    monkeypatch.setattr(client, "urlopen", lambda *_args, **_kwargs: stream(*events))
    with pytest.raises(client.TinyFishError) as error:
        client.run_agent(URL, "stage only", progress=lambda _: None)
    assert "private key" not in str(error.value)
    assert len(mocked_agent) == 1


def test_http_errors_do_not_echo_response_bodies(monkeypatch, mocked_agent):
    def broken(*args, **kwargs):
        raise HTTPError(URL, 403, "forbidden", {}, io.BytesIO(b"mock-key-never-live"))
    monkeypatch.setattr(client, "urlopen", broken)
    with pytest.raises(client.TinyFishError, match="HTTP 403") as error:
        client.run_agent(URL, "stage only", progress=lambda _: None)
    assert "mock-key" not in str(error.value)


def test_total_deadline_stops_stream_and_cancels_known_run(monkeypatch, mocked_agent):
    ticks = iter([0, 0, 1, 1, 141])
    monkeypatch.setattr(client.time, "monotonic", lambda: next(ticks))
    monkeypatch.setattr(client, "urlopen", lambda *_args, **_kwargs: stream(
        {"type": "STARTED", "run_id": "run_1"}, {"type": "HEARTBEAT"}))
    with pytest.raises(client.TinyFishError, match="run limit"):
        client.run_agent(URL, "stage only", progress=lambda _: None)
    assert mocked_agent == ["run_1"]


def test_legacy_public_checkout_blocks_before_key_or_paid_call(monkeypatch):
    calls = []
    def urlopen(url, timeout):
        calls.append(url)
        return Response(b'<button id="confirm">Confirm booking</button>')
    monkeypatch.setattr(client, "urlopen", urlopen)
    monkeypatch.setattr(client, "_load_key", lambda: pytest.fail("Must not load/use a key for an unprotected site"))
    with pytest.raises(client.TinyFishError, match="No paid agent call"):
        client.run_agent(URL, "stage only")
    assert calls == ["https://demo-booking-tau.vercel.app/checkout.html"]


@pytest.mark.parametrize("url", [
    "http://localhost/", "https://demo-booking-tau.vercel.app.evil.example/",
    "https://demo-booking-tau.vercel.app@evil.example/", "https://demo-booking-tau.vercel.app/.env",
])
def test_live_url_allowlist_is_exact(url):
    with pytest.raises(client.TinyFishError):
        client.validate_demo_url(url)


def test_single_live_smoke_does_not_retry_invalid_extraction(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(staging, "_RECORDINGS", tmp_path)
    monkeypatch.setattr(staging, "run_agent", lambda *_: calls.append(1) or {"result": {"cart": None}})
    with pytest.raises(staging.StagingError, match="single-run limit"):
        staging.stage_cart_evidence(URL, DEMO_CONTRACT, max_attempts=1, replay=False)
    assert calls == [1]


def test_invalid_replay_path_is_rejected():
    with pytest.raises(staging.StagingError, match="Invalid replay"):
        staging._load_recording("../outside")
