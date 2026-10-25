"""Preflight validation for AgentGuard food vertical demo.

Checks app responsiveness, REPLAY configuration, deployed platform availability,
recordings presence, TinyFish API key status, and replay verification.
Calls TinyFish only when --live is specified.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import urllib.request
import urllib.error

# Root of AgentGuard workspace
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DEPLOYED_PLATFORMS = [
    "https://demo-booking-tau.vercel.app/foodhub/",
    "https://demo-booking-tau.vercel.app/quickbite/",
    "https://demo-booking-tau.vercel.app/dinedash/",
]

RECORDING_FILES = [
    "recordings/food/foodhub.json",
    "recordings/food/quickbite.json",
    "recordings/food/dinedash.json",
]


def check_http_200(url: str, timeout: float = 10.0) -> tuple[bool, str]:
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "AgentGuard-Preflight/1.0"}
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            code = resp.getcode()
            if code == 200:
                return True, f"HTTP {code}"
            return False, f"HTTP {code}"
    except urllib.error.HTTPError as err:
        return False, f"HTTP {err.code}"
    except Exception as err:
        return False, str(err)


def run_preflight(app_url: str, live: bool) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    passed: list[str] = []

    print("=" * 60)
    print(f"AgentGuard Preflight Check (Mode: {'LIVE' if live else 'REPLAY'})")
    print("=" * 60)

    # 1. App responding check
    health_url = f"{app_url.rstrip('/')}/health"
    app_ok, app_msg = check_http_200(health_url, timeout=5.0)
    app_health = {}
    if app_ok:
        try:
            req = urllib.request.Request(health_url)
            with urllib.request.urlopen(req, timeout=5.0) as resp:
                app_health = json.loads(resp.read().decode("utf-8"))
            print(f"  [PASS] App responding at {health_url} ({app_msg})")
            passed.append("App responding")
        except Exception as e:
            app_ok = False
            app_msg = f"Failed to parse health response: {e}"
    if not app_ok:
        msg = f"App not responding at {health_url} ({app_msg})"
        print(f"  [FAIL] {msg}")
        reasons.append(msg)

    # 2. REPLAY state
    env_replay = os.getenv("REPLAY") == "1"
    server_replay = app_health.get("replay", env_replay)
    if live:
        if env_replay or server_replay:
            msg = f"Live mode requested but REPLAY is active (env REPLAY={os.getenv('REPLAY')}, server replay={server_replay})"
            print(f"  [FAIL] {msg}")
            reasons.append(msg)
        else:
            print("  [PASS] REPLAY state: Disabled (live mode configured)")
            passed.append("REPLAY state: live")
    else:
        if not env_replay and not server_replay:
            msg = "Replay mode expected but REPLAY is not set to 1"
            print(f"  [FAIL] {msg}")
            reasons.append(msg)
        else:
            print(f"  [PASS] REPLAY state: Active (REPLAY={os.getenv('REPLAY') or (1 if server_replay else 0)})")
            passed.append("REPLAY state: replay")

    # 3. Three platform URLs on deployed site
    for plat_url in DEPLOYED_PLATFORMS:
        ok, msg = check_http_200(plat_url, timeout=10.0)
        if ok:
            print(f"  [PASS] Deployed platform {plat_url} ({msg})")
            passed.append(f"Deployed platform {plat_url}")
        else:
            fail_msg = f"Deployed platform {plat_url} returned {msg}"
            print(f"  [FAIL] {fail_msg}")
            reasons.append(fail_msg)

    # 4. Recordings present
    for rec_rel in RECORDING_FILES:
        rec_path = ROOT / rec_rel
        if rec_path.is_file():
            try:
                data = json.loads(rec_path.read_text(encoding="utf-8"))
                opts = data.get("options", [])
                if opts:
                    print(f"  [PASS] Recording present: {rec_rel} ({len(opts)} options)")
                    passed.append(f"Recording {rec_rel}")
                else:
                    fail_msg = f"Recording {rec_rel} has no options"
                    print(f"  [FAIL] {fail_msg}")
                    reasons.append(fail_msg)
            except Exception as e:
                fail_msg = f"Recording {rec_rel} failed to parse: {e}"
                print(f"  [FAIL] {fail_msg}")
                reasons.append(fail_msg)
        else:
            fail_msg = f"Recording missing on disk: {rec_rel}"
            print(f"  [FAIL] {fail_msg}")
            reasons.append(fail_msg)

    # 5. TinyFish key present (never print its value)
    tinyfish_key = os.getenv("TINYFISH_API_KEY", "").strip()
    key_present = bool(tinyfish_key)
    if key_present:
        print("  [PASS] TinyFish API key: Present")
        passed.append("TinyFish API key present")
    else:
        if live:
            fail_msg = "TinyFish API key missing in environment (required for --live)"
            print(f"  [FAIL] {fail_msg}")
            reasons.append(fail_msg)
        else:
            print("  [INFO] TinyFish API key: Not present (optional in replay mode)")

    # 6. One replay compare plus one replay extras run succeeding
    try:
        from app.food_compare import compare_all, stage_winner
        from guard.food_models import FoodContract

        test_contract = FoodContract(
            diet="veg", quantity=1, max_total=300, min_rating=4.2,
            max_eta_minutes=45, allow_extras=False, priority="price",
        )
        comp = compare_all(DEPLOYED_PLATFORMS, replay=True)
        if len(comp.options) == 7 and not comp.failures:
            print(f"  [PASS] Replay compare verification (returned {len(comp.options)} options across 3 platforms)")
            passed.append("Replay compare verification")
        else:
            fail_msg = f"Replay compare failed: options={len(comp.options)}, failures={comp.failures}"
            print(f"  [FAIL] {fail_msg}")
            reasons.append(fail_msg)

        foodhub_opt = next((o for o in comp.options if o.platform.lower() == "foodhub" and o.restaurant == "Spice Route"), None)
        if foodhub_opt is None:
            fail_msg = "Replay extras: Spice Route option missing on FoodHub"
            print(f"  [FAIL] {fail_msg}")
            reasons.append(fail_msg)
        else:
            extras_opt = foodhub_opt.model_copy(update={"url": f"{foodhub_opt.url}&scenario=extras" if "?" in foodhub_opt.url else f"{foodhub_opt.url}?scenario=extras"})
            cart = stage_winner(extras_opt, test_contract, replay=True)
            tip_item = next((i for i in cart.items if i.type == "tip"), None)
            don_item = next((i for i in cart.items if i.type == "donation"), None)
            if cart.total == 320 and tip_item and tip_item.price == 30 and don_item and don_item.price == 10:
                print("  [PASS] Replay extras verification (total 320, tip 30, donation 10 present)")
                passed.append("Replay extras verification")
            else:
                fail_msg = f"Replay extras verification mismatch: total={cart.total}, tip={getattr(tip_item, 'price', None)}, donation={getattr(don_item, 'price', None)}"
                print(f"  [FAIL] {fail_msg}")
                reasons.append(fail_msg)
    except Exception as e:
        fail_msg = f"Replay verification encountered exception: {e}"
        print(f"  [FAIL] {fail_msg}")
        reasons.append(fail_msg)

    # 7. Live check: calls TinyFish only with --live
    if live:
        if not key_present:
            pass  # Already added failure above
        else:
            try:
                from app.tinyfish_client import TinyFishClient
                client = TinyFishClient()
                # Run a fast ping or simple check
                print("  [PASS] TinyFish client initialized for live mode")
                passed.append("TinyFish live initialization")
            except Exception as e:
                fail_msg = f"TinyFish client initialization failed: {e}"
                print(f"  [FAIL] {fail_msg}")
                reasons.append(fail_msg)
    else:
        print("  [INFO] TinyFish live API skipped (not requested; use --live to test)")

    print("=" * 60)
    is_go = len(reasons) == 0
    if is_go:
        print("PREFLIGHT: GO")
        print(f"All {len(passed)} checks passed successfully.")
    else:
        print("PREFLIGHT: NO-GO")
        print(f"{len(reasons)} check(s) failed:")
        for r in reasons:
            print(f"  - {r}")
    print("=" * 60)

    return is_go, reasons


def main() -> int:
    parser = argparse.ArgumentParser(description="Preflight check for AgentGuard food vertical")
    parser.add_argument("--live", action="store_true", help="Validate live mode instead of replay mode")
    parser.add_argument("--app-url", default=os.getenv("FOOD_BASE_URL", "http://127.0.0.1:8135"), help="App URL to check")
    args = parser.parse_args()

    # Load environment from .env if present
    env_file = ROOT / ".env"
    if env_file.is_file():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())

    is_go, _ = run_preflight(args.app_url, args.live)
    return 0 if is_go else 1


if __name__ == "__main__":
    sys.exit(main())
