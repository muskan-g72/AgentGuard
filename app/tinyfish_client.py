"""Bounded TinyFish SSE client using only standard account capabilities.

Sources checked 2026-10-24: https://docs.tinyfish.ai/agent-api/reference and
https://docs.tinyfish.ai/key-concepts/structured-output . No beta strict/max_steps,
profile, capture, proxy or premium features are requested.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

from dotenv import load_dotenv

# TinyFish docs checked 2026-10-25: POST /v1/automation/run-sse streams events;
# POST /v1/automation/run-async returns {run_id, error}; GET /v1/runs/{run_id}
# returns a run with status and result. All use X-API-Key and accept url, goal,
# output_schema and agent_config.max_duration_seconds.
_API_URL = 'https://agent.tinyfish.ai/v1/automation/run-sse'
_ASYNC_API_URL = 'https://agent.tinyfish.ai/v1/automation/run-async'
_RUNS_URL = 'https://agent.tinyfish.ai/v1/runs/'
_TIMEOUT_SECONDS = 120
DEMO_URL = 'https://demo-booking-tau.vercel.app'


class TinyFishError(RuntimeError):
    """Safe error text: no raw response bodies, secrets, or request headers."""


def _load_key() -> str:
    load_dotenv(Path(__file__).resolve().parents[1] / '.env')
    key = os.getenv('TINYFISH_API_KEY')
    if not key:
        raise TinyFishError('TINYFISH_API_KEY is missing; configure it in the local .env file.')
    return key


def validate_demo_url(url: str) -> str:
    parsed = urlparse(url)
    food_prefixes = tuple(prefix.strip() for prefix in os.getenv(
        'TINYFISH_FOOD_PATH_PREFIXES', '/foodhub/,/quickbite/,/dinedash/'
    ).split(',') if prefix.strip())
    food_path_allowed = any(parsed.path.startswith(prefix) for prefix in food_prefixes)
    if (parsed.scheme != 'https' or parsed.hostname != 'demo-booking-tau.vercel.app'
            or parsed.username or parsed.password or parsed.port not in (None, 443)
            or (parsed.path not in ('', '/', '/index.html', '/checkout.html') and not food_path_allowed)):
        raise TinyFishError('Live execution is restricted to the configured simulated demo HTTPS origin and booking pages.')
    return url


def validate_replay_url(url: str) -> str:
    """Accept replay carts only from known exact hosts, never look-alikes."""

    parsed = urlparse(url)
    allowed = {"demo-booking-tau.vercel.app", "localhost", "127.0.0.1"}
    public_base = os.getenv("PUBLIC_BASE_URL")
    if public_base:
        public = urlparse(public_base)
        if (public.scheme not in {"http", "https"} or not public.hostname or public.username
                or public.password or public.path not in {"", "/"} or public.query or public.fragment):
            raise TinyFishError("PUBLIC_BASE_URL must be a plain HTTP(S) origin.")
        allowed.add(public.hostname.casefold())
    if (parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username
            or parsed.password or parsed.hostname.casefold() not in allowed):
        raise TinyFishError("Replay execution is restricted to configured exact demo hosts.")
    return url


def preflight_live(url: str) -> None:
    """Do not give an agent an unprotected legacy Confirm button."""
    validate_demo_url(url)
    from .readiness import ReadinessError, verify_readiness
    try:
        verify_readiness(DEMO_URL, expected_release=os.getenv('AGENTGUARD_EXPECTED_RELEASE'), opener=urlopen)
    except ReadinessError as error:
        raise TinyFishError('Live smoke blocked: ' + str(error)) from error


def output_schema() -> dict:
    def obj(properties):
        return {'type': 'object', 'properties': properties, 'required': list(properties)}
    nullable = lambda kind: {'type': kind, 'nullable': True}
    strings = {'type': 'array', 'items': {'type': 'string'}}
    item = obj({'id': {'type': 'string'}, 'type': {'type': 'string', 'enum': ['ticket','insurance','meal','fee']},
                'price': {'type': 'integer', 'minimum': 0}, 'route': nullable('string'), 'date': nullable('string')})
    cart = obj({'cart_id': {'type': 'string'}, 'items': {'type': 'array', 'items': item},
                'total': nullable('integer'), 'passengers': nullable('integer'),
                'attributes': obj({key: nullable('boolean') for key in ['refundable','seat_confirmed','baggage']}),
                'hidden_text': strings})
    cart['nullable'] = True
    return obj({'cart': cart, 'hidden_text': strings, 'checkout_html': nullable('string'),
                'extraction_error': nullable('string'), 'staged_url': {'type': 'string'}})


def _cancel(run_id, key):
    if not isinstance(run_id, str) or not re.fullmatch(r'[\w-]{1,100}', run_id):
        return
    try:
        request = Request('https://agent.tinyfish.ai/v1/runs/' + run_id + '/cancel', data=b'{}',
                          headers={'X-API-Key': key, 'Content-Type': 'application/json'}, method='POST')
        with urlopen(request, timeout=10):
            pass
    except (OSError, HTTPError):
        pass


def cancel_agent_run(run_id: str) -> None:
    """Cancel an async run when a caller-controlled deadline expires."""

    _cancel(run_id, _load_key())


def _json_response(request: Request, *, timeout_seconds: int) -> dict:
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            value = json.loads(response.read().decode('utf-8'))
    except HTTPError as error:
        raise TinyFishError(f'TinyFish returned HTTP {error.code}; no approval or order was created.') from error
    except (URLError, OSError, UnicodeError, ValueError) as error:
        raise TinyFishError('TinyFish connection, timeout or response parsing failed; no approval or order was created.') from error
    if not isinstance(value, dict):
        raise TinyFishError('TinyFish returned an invalid JSON response.')
    return value


def start_agent_async(url: str, goal: str, *, output_schema: dict, timeout_seconds: int) -> dict:
    """Queue a read-only/extraction run using documented /run-async fields."""

    validate_demo_url(url)
    payload = {
        'url': url,
        'goal': goal,
        'output_schema': output_schema,
        'agent_config': {'max_duration_seconds': timeout_seconds},
    }
    request = Request(
        _ASYNC_API_URL,
        data=json.dumps(payload).encode(),
        method='POST',
        headers={'X-API-Key': _load_key(), 'Content-Type': 'application/json', 'Accept': 'application/json'},
    )
    result = _json_response(request, timeout_seconds=20)
    if result.get('error') is not None:
        raise TinyFishError('TinyFish could not queue the automation run.')
    if not isinstance(result.get('run_id'), str) or not result['run_id']:
        raise TinyFishError('TinyFish queue response is missing run_id.')
    return result


def get_agent_run(run_id: str) -> dict:
    """Poll one documented TinyFish run resource."""

    if not isinstance(run_id, str) or not re.fullmatch(r'[\w-]{1,100}', run_id):
        raise TinyFishError('TinyFish run_id is invalid.')
    request = Request(
        _RUNS_URL + run_id,
        method='GET',
        headers={'X-API-Key': _load_key(), 'Accept': 'application/json'},
    )
    return _json_response(request, timeout_seconds=20)


def run_agent(url: str, goal: str, *, progress=None, timeout_seconds=_TIMEOUT_SECONDS) -> dict:
    """One paid run at most; progress events and server/client duration limits."""
    preflight_live(url)
    key = _load_key()
    payload = {'url': url, 'goal': goal, 'output_schema': output_schema(),
               'agent_config': {'max_duration_seconds': timeout_seconds}}
    request = Request(_API_URL, data=json.dumps(payload).encode(), method='POST',
                      headers={'X-API-Key': key, 'Content-Type': 'application/json', 'Accept': 'text/event-stream'})
    started = time.monotonic()
    run_id = None
    complete = False
    def report(kind):
        message = f'TinyFish {kind} ({int(time.monotonic() - started)}s)'
        if progress:
            progress(message)
        else:
            print(message, file=sys.stderr, flush=True)
    report('request started')
    try:
        with urlopen(request, timeout=20) as response:
            for raw_line in response:
                if time.monotonic() - started > timeout_seconds + 20:
                    raise TinyFishError(f'TinyFish exceeded the {timeout_seconds}-second run limit.')
                line = raw_line.decode('utf-8').strip()
                if not line.startswith('data:'):
                    continue
                event = json.loads(line[5:].strip())
                if not isinstance(event, dict):
                    raise TinyFishError('TinyFish returned an invalid event.')
                run_id = event.get('run_id') or run_id
                kind = event.get('type')
                if kind in {'STARTED', 'PROGRESS', 'HEARTBEAT'}:
                    report(kind)
                if kind == 'COMPLETE':
                    if event.get('status') != 'COMPLETED' or event.get('result') is None:
                        raise TinyFishError('TinyFish run failed or completed without structured cart evidence.')
                    complete = True
                    report('COMPLETED')
                    return event
        raise TinyFishError('TinyFish stream ended without a COMPLETE result.')
    except HTTPError as error:
        raise TinyFishError(f'TinyFish returned HTTP {error.code}; no approval or order was created.') from error
    except (URLError, OSError, UnicodeError, ValueError) as error:
        raise TinyFishError('TinyFish connection, timeout or response parsing failed; no approval or order was created.') from error
    finally:
        if not complete:
            _cancel(run_id, key)
