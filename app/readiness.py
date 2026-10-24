"""Read-only deployment verification. Never calls an agent or creates an order."""

import json
import time
from urllib.error import HTTPError
from urllib.parse import urlparse
from urllib.request import urlopen

from .release import ASSETS, sha256


class ReadinessError(RuntimeError):
    pass


def verify_readiness(base_url: str, *, expected_release=None, require_durable=True,
                     require_proxy=True, expected_public_origin=None, opener=urlopen) -> dict:
    base_url = base_url.rstrip("/")
    origin = urlparse(base_url)
    if not origin.hostname or origin.path or origin.query or origin.fragment or origin.username or origin.password:
        raise ReadinessError("Supply a base origin without path, credentials or query parameters.")
    if origin.scheme != "https" and (require_durable or origin.hostname not in {"127.0.0.1", "localhost"}):
        raise ReadinessError("Public verification requires HTTPS.")
    deadline = time.monotonic() + 45

    def get(path):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise ReadinessError("Deployment verification exceeded its 45-second deadline.")
        try:
            with opener(base_url + path, timeout=min(10, remaining)) as response:
                final = urlparse(response.geturl()) if hasattr(response, "geturl") else origin
                if (final.scheme, final.netloc) != (origin.scheme, origin.netloc):
                    raise ReadinessError("A public verification endpoint redirected to another origin.")
                body = response.read(2_000_001)
                if len(body) > 2_000_000:
                    raise ReadinessError("Deployment evidence exceeded the size limit.")
                return getattr(response, "status", 200), body, dict(getattr(response, "headers", {}))
        except HTTPError as error:
            return error.code, b"", {}
        except (OSError, ValueError) as error:
            raise ReadinessError("Could not read deployment evidence; no agent run was started.") from error

    def document(path):
        status, body, _ = get(path)
        if status != 200:
            raise ReadinessError(f"Required protected endpoint {path} returned HTTP {status}.")
        try:
            value = json.loads(body)
        except (ValueError, UnicodeError) as error:
            raise ReadinessError(f"Required endpoint {path} did not return JSON.") from error
        if not isinstance(value, dict):
            raise ReadinessError(f"Required endpoint {path} did not return an object.")
        return value

    status, checkout, _ = get("/checkout.html")
    if status != 200 or b'data-confirmation-protected="true"' not in checkout:
        raise ReadinessError("Hosted checkout has no protected server-backed Confirm button. No paid agent call was made.")
    version = document("/version")
    health = document("/health")
    if (version.get("workflow") != "protected-v2" or not version.get("release_id")
            or health.get("release_id") != version["release_id"]
            or expected_release is not None and version["release_id"] != expected_release):
        raise ReadinessError("The served backend release differs from the expected protected release.")
    if not all(health.get(key) is True for key in (
        "db_ok", "checker_available", "confirmation_protected", "receipt_configured",
    )):
        raise ReadinessError(
            "The authoritative database, checker, protected confirmation, or receipt signer is unavailable."
        )
    storage = health.get("storage", {})
    if not isinstance(storage, dict) or not storage.get("storage_id"):
        raise ReadinessError("The server did not identify its authoritative persistent database.")
    if require_durable and (storage.get("durable") is not True or health.get("public_origin") != (expected_public_origin or base_url)):
        raise ReadinessError("The public backend is not using verified durable storage for this origin.")
    if require_proxy:
        descriptor = document("/deployment.json")
        for key in ("release_id", "frontend_sha256", "backend_sha256"):
            if descriptor.get(key) != version.get(key):
                raise ReadinessError("The Vercel proxy descriptor and running backend versions disagree.")
        if descriptor.get("public_origin") != base_url:
            raise ReadinessError("The Vercel descriptor identifies another public origin.")
    assets = version.get("assets")
    if not isinstance(assets, dict) or set(assets) != set(ASSETS):
        raise ReadinessError("The backend did not provide the complete frontend asset manifest.")
    for name, fingerprint in assets.items():
        status, body, _ = get("/" + name)
        if status != 200 or sha256(body) != fingerprint:
            raise ReadinessError(f"Public frontend asset {name} differs from the running backend release.")
    status, _, _ = get("/api/orders/order_preflight_nonexistent")
    if status != 404:
        raise ReadinessError("The order endpoint does not reject an unknown server order.")
    return {"ready": True, "release_id": version["release_id"],
            "frontend_sha256": version["frontend_sha256"], "backend_sha256": version["backend_sha256"],
            "storage_id": storage["storage_id"], "instance_id": health.get("instance_id"),
            "durable": storage.get("durable") is True, "note": "Read-only preflight; no paid agent or order was executed."}
