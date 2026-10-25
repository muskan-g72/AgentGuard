"""Explicit public origins and fail-closed durable SQLite configuration."""

from dataclasses import dataclass
import os
from pathlib import Path
import re
from urllib.parse import urlparse


PUBLIC_ORIGIN = "https://demo-booking-tau.vercel.app"


def exact_host(value: str) -> str:
    if not re.fullmatch(r"[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?", value) or ".." in value:
        raise ValueError("Configure a literal lowercase hostname without scheme, port or wildcard.")
    return value


def configured_hosts() -> set[str]:
    """Read only literal hostnames from deployment configuration."""
    hosts = set()
    for value in os.getenv("ALLOWED_HOSTS", "").split(","):
        value = value.strip()
        if value:
            hosts.add(exact_host(value))

    public_base = os.getenv("PUBLIC_BASE_URL")
    if public_base:
        parsed = urlparse(public_base)
        if (parsed.scheme not in {"http", "https"} or not parsed.hostname
                or parsed.username or parsed.password or parsed.path not in {"", "/"}
                or parsed.query or parsed.fragment):
            raise ValueError("PUBLIC_BASE_URL must be a plain HTTP(S) origin.")
        hosts.add(exact_host(parsed.hostname.casefold()))
    return hosts


@dataclass(frozen=True)
class Settings:
    database: Path
    allowed_hosts: frozenset[str]
    public_origin: str
    durable: bool
    agent_runs_enabled: bool

    @classmethod
    def load(cls, root: Path, database=None):
        durable = os.getenv("AGENTGUARD_DEPLOYMENT_MODE", "local") == "durable"
        if os.getenv("AGENTGUARD_DEPLOYMENT_MODE", "local") not in {"local", "durable"}:
            raise ValueError("AGENTGUARD_DEPLOYMENT_MODE must be local or durable.")
        if os.getenv("VERCEL"):
            raise ValueError("SQLite authority cannot run in Vercel Functions; use the durable backend and proxy deployment.")
        public = os.getenv("AGENTGUARD_PUBLIC_ORIGIN", PUBLIC_ORIGIN if durable else "http://127.0.0.1:8001")
        parsed = urlparse(public)
        if (parsed.scheme not in ({"https"} if durable else {"http", "https"}) or not parsed.hostname
                or parsed.username or parsed.password or parsed.path not in {"", "/"} or parsed.query or parsed.fragment
                or durable and parsed.port not in {None, 443}):
            raise ValueError("AGENTGUARD_PUBLIC_ORIGIN must be an origin, using HTTPS in durable mode.")
        hosts = {"localhost", "127.0.0.1", exact_host(parsed.hostname)}
        hosts.update(configured_hosts())
        backend = os.getenv("AGENTGUARD_BACKEND_HOST")
        if backend:
            hosts.add(exact_host(backend))
        path = Path(database or os.getenv("AGENTGUARD_DB", str(root / "data" / "workflow.db")))
        if durable:
            mount = Path(os.getenv("AGENTGUARD_VOLUME_PATH", "/data")).resolve()
            if not path.is_absolute() or not path.resolve().is_relative_to(mount) or not mount.is_mount():
                raise ValueError("Durable mode requires an absolute AGENTGUARD_DB inside a real mounted AGENTGUARD_VOLUME_PATH.")
        return cls(path, frozenset(hosts), public.rstrip("/"), durable,
                   os.getenv("AGENTGUARD_ENABLE_AGENT_RUNS", "false" if durable else "true") == "true")
