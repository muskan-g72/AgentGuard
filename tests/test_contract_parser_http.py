"""Mocked raw Responses API bodies; these are not live LLM evidence."""

import io
import json

import pytest

from guard import contract_parser as parser
from scripts import llm_smoke


class Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


def complete():
    contract = parser.DEMO_CONTRACT.model_dump()
    contract.update(date="2026-10-26", quantity=2, max_total=2500, source="parsed")
    contract["requirements"] = {"refundable": False, "seat_confirmed": True, "baggage": None}
    return {"status": "completed", "output": [{"type": "reasoning"}, {
        "type": "message", "role": "assistant", "content": [{"type": "output_text", "text": json.dumps(contract)}]}]}


def test_raw_response_array_parses_without_sdk_output_text(monkeypatch):
    calls = []
    monkeypatch.setenv("OPENAI_API_KEY", "mock-key")
    def urlopen(request, timeout):
        calls.append((json.loads(request.data), timeout))
        return Response(json.dumps(complete()).encode())
    monkeypatch.setattr(parser, "urlopen", urlopen)
    result = parser.parse_contract(llm_smoke.SENTENCE)
    assert result.source == "parsed"
    assert (result.date, result.quantity, result.max_total) == ("2026-10-26", 2, 2500)
    assert result.requirements.refundable is False
    assert len(calls) == 1 and calls[0][1] == 10
    assert calls[0][0]["max_output_tokens"] == 1000
    schema = calls[0][0]["text"]["format"]["schema"]
    assert schema["properties"]["max_total"]["type"] == "integer"
    assert schema["required"] == list(schema["properties"])


@pytest.mark.parametrize("issue", ["incomplete", "failed", "refusal", "no_output", "invalid_json", "decimal_money"])
def test_unsuccessful_api_drafts_remain_explicit_fallbacks(monkeypatch, issue):
    body = complete()
    if issue in {"incomplete", "failed"}:
        body["status"] = issue
    elif issue == "refusal":
        body["output"][1]["content"] = [{"type": "refusal", "refusal": "No"}]
    elif issue == "no_output":
        body["output"] = []
    elif issue == "invalid_json":
        body["output"][1]["content"][0]["text"] = "{bad"
    else:
        text = json.loads(body["output"][1]["content"][0]["text"])
        text["max_total"] = 2500.0
        body["output"][1]["content"][0]["text"] = json.dumps(text)
    monkeypatch.setenv("OPENAI_API_KEY", "mock-key")
    monkeypatch.setattr(parser, "urlopen", lambda *_a, **_kw: Response(json.dumps(body).encode()))
    assert parser.parse_contract("draft").source == "fallback"


def test_smoke_needs_explicit_opt_in_even_when_a_key_exists(monkeypatch, capsys):
    monkeypatch.setenv("OPENAI_API_KEY", "mock-key")
    monkeypatch.setattr(llm_smoke, "parse_contract", lambda *_: pytest.fail("No API call without --live"))
    assert llm_smoke.main([]) == 2
    assert json.loads(capsys.readouterr().out)["status"] == "not_run"


@pytest.mark.parametrize("source,code,status", [("parsed", 0, "api_parsed_draft"), ("fallback", 1, "fallback_demo_contract")])
def test_smoke_exit_code_does_not_treat_fallback_as_api_success(monkeypatch, capsys, source, code, status):
    monkeypatch.setenv("OPENAI_API_KEY", "mock-key")
    monkeypatch.setattr(llm_smoke, "load_dotenv", lambda *_: None)
    monkeypatch.setattr(llm_smoke, "parse_contract", lambda *_: parser.DEMO_CONTRACT.model_copy(update={"source": source}))
    assert llm_smoke.main(["--live"]) == code
    output = capsys.readouterr().out
    result = json.loads(output)
    assert result["status"] == status
    assert result["api_parse_succeeded"] == (source == "parsed")
    assert "mock-key" not in output
