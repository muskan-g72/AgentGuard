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

_API_URL = 'https://agent.tinyfish.ai/v1/automation/run-sse'
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
    if (parsed.scheme != 'https' or parsed.hostname != 'demo-booking-tau.vercel.app'
            or parsed.username or parsed.password or parsed.port not in (None, 443)
            or parsed.path not in ('', '/', '/index.html', '/checkout.html')):
        raise TinyFishError('Live execution is restricted to the configured simulated demo HTTPS origin and booking pages.')
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
