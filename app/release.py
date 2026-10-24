"""Content identities for the exact source and UI served by this backend."""

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ASSETS = ("index.html", "checkout.html", "confirmation.html", "app.js", "checkout.js", "styles.css")


def sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _identity(values: dict) -> str:
    return sha256(json.dumps(values, sort_keys=True, separators=(",", ":")).encode())


def release(root=ROOT) -> dict:
    assets = {name: sha256((root / name).read_bytes()) for name in ASSETS}
    files = [root / "pyproject.toml", root / "requirements-deploy.txt"]
    files += sorted((root / "app").glob("*.py")) + sorted((root / "guard").glob("*.py"))
    backend = {file.relative_to(root).as_posix(): sha256(file.read_bytes()) for file in files if file.exists()}
    frontend_sha = _identity(assets)
    backend_sha = _identity(backend)
    return {"workflow": "protected-v2", "release_id": _identity({"frontend": frontend_sha, "backend": backend_sha}),
            "frontend_sha256": frontend_sha, "backend_sha256": backend_sha, "assets": assets}
