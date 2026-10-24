"""Generate local Fly and prebuilt Vercel proxy files. Never creates/deploys resources."""

import argparse
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.config import PUBLIC_ORIGIN
from app.release import release


def prepare(app: str, region: str, root=ROOT):
    if not re.fullmatch(r"[a-z][a-z0-9-]{2,49}", app) or "--" in app:
        raise ValueError("Supply a valid, explicitly chosen Fly app name.")
    if not re.fullmatch(r"[a-z]{3}", region):
        raise ValueError("Supply a three-letter Fly region code.")
    config = root / "deploy" / "fly.toml.template"
    generated = root / "deploy" / "generated"
    generated.mkdir(parents=True, exist_ok=True)
    (generated / "fly.toml").write_text(config.read_text(encoding="utf-8").replace("__APP__", app).replace("__REGION__", region), encoding="utf-8")
    version = release(root)
    descriptor = {**version, "public_origin": PUBLIC_ORIGIN, "backend_origin": f"https://{app}.fly.dev"}
    (generated / "release.json").write_text(json.dumps(descriptor, indent=2) + "\n", encoding="utf-8")
    output = root / ".vercel" / "output"
    (output / "static").mkdir(parents=True, exist_ok=True)
    # An unknown stale function/static asset must never shadow the proxy.
    if (output / "functions").exists() or any(path.name != "deployment.json" for path in (output / "static").iterdir()):
        raise ValueError("Vercel output contains unrelated artifacts. Use a clean output directory; no files were deleted.")
    (output / "static" / "deployment.json").write_text(json.dumps(descriptor, indent=2) + "\n", encoding="utf-8")
    headers = {"Cache-Control": "no-store", "CDN-Cache-Control": "no-store",
               "Vercel-CDN-Cache-Control": "no-store", "x-vercel-enable-rewrite-caching": "0"}
    proxy = {"version": 3, "routes": [
        {"src": "^/deployment\\.json$", "dest": "/deployment.json", "headers": headers},
        {"src": "^/(.*)$", "dest": f"https://{app}.fly.dev/$1", "headers": headers},
    ]}
    (output / "config.json").write_text(json.dumps(proxy, indent=2) + "\n", encoding="utf-8")
    return {"release_id": version["release_id"], "backend_origin": descriptor["backend_origin"],
            "fly_config": str(generated / "fly.toml"), "vercel_output": str(output),
            "note": "Prepared locally only. No Fly app, volume or Vercel deployment was created."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app", required=True)
    parser.add_argument("--region", default="sin")
    args = parser.parse_args()
    print(json.dumps(prepare(args.app, args.region), indent=2))


if __name__ == "__main__":
    main()
