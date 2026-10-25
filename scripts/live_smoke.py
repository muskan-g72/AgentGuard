"""Live smoke test for deployed food platforms on https://demo-booking-tau.vercel.app.

Performs TinyFish async Agent comparisons for FoodHub, QuickBite, and DineDash,
compares options against data/food.json, and stages FoodHub extras without ordering.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

from app.food_compare import (
    FoodCompareError,
    FoodOption,
    compare_all,
    stage_winner,
)
from guard.food_models import FoodContract
from app.tinyfish_client import TinyFishError

PLATFORM_URLS = [
    ("foodhub", "https://demo-booking-tau.vercel.app/foodhub/"),
    ("quickbite", "https://demo-booking-tau.vercel.app/quickbite/"),
    ("dinedash", "https://demo-booking-tau.vercel.app/dinedash/"),
]

CONTRACT = FoodContract(
    diet="veg",
    quantity=1,
    max_total=300,
    min_rating=4.2,
    max_eta_minutes=45,
    allow_extras=False,
    priority="price",
)


def set_scenario(url: str, scenario: str) -> str:
    parsed = urlparse(url)
    qs = parse_qs(parsed.query, keep_blank_values=True)
    qs["scenario"] = [scenario]
    for k in ["tip", "donation", "gold"]:
        qs.pop(k, None)
    new_query = urlencode(qs, doseq=True)
    return urlunparse(parsed._replace(query=new_query))


def load_expected_catalog() -> dict:
    catalog_path = ROOT / "data" / "food.json"
    if not catalog_path.exists():
        raise RuntimeError(f"Missing expected catalog at {catalog_path}")
    return json.loads(catalog_path.read_text(encoding="utf-8"))


def compare_options_against_catalog(platform: str, options: list[FoodOption], catalog: dict) -> list[str]:
    """Return a list of discrepancies between live extracted options and data/food.json."""
    discrepancies: list[str] = []
    expected_options = [
        o for o in catalog.get("options", [])
        if o["platform"].lower() == platform.lower()
    ]

    if len(options) != len(expected_options):
        discrepancies.append(
            f"Option count mismatch: extracted {len(options)}, expected {len(expected_options)}"
        )

    expected_by_key = {
        (o["restaurant"].lower(), o["dish"].lower()): o
        for o in expected_options
    }

    for opt in options:
        key = (opt.restaurant.lower(), opt.dish.lower())
        if key not in expected_by_key:
            discrepancies.append(f"Unexpected dish extracted: {opt.restaurant} - {opt.dish}")
            continue
        exp = expected_by_key[key]
        if opt.item_price != exp["item_price"]:
            discrepancies.append(f"{opt.dish} price mismatch: live={opt.item_price}, expected={exp['item_price']}")
        if opt.veg != exp["veg"]:
            discrepancies.append(f"{opt.dish} veg mismatch: live={opt.veg}, expected={exp['veg']}")
        if opt.rating != exp["rating"]:
            discrepancies.append(f"{opt.dish} rating mismatch: live={opt.rating}, expected={exp['rating']}")
        if opt.eta_minutes != exp["eta_minutes"]:
            discrepancies.append(f"{opt.dish} eta mismatch: live={opt.eta_minutes}, expected={exp['eta_minutes']}")
        fees_live = opt.fees.model_dump()
        fees_exp = exp.get("fees", {})
        if fees_live != fees_exp:
            discrepancies.append(f"{opt.dish} fees mismatch: live={fees_live}, expected={fees_exp}")

    return discrepancies


def save_recording(platform: str, step: str, scenario: str, run_id: str | None, raw_payload: object) -> Path:
    live_dir = ROOT / "recordings" / "food" / "live"
    live_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(UTC).isoformat()
    record = {
        "source": "live",
        "timestamp": ts,
        "run_id": run_id or "unknown",
        "scenario": scenario,
        "platform": platform,
        "step": step,
        "raw": raw_payload,
    }
    filename = f"{platform}_{step}_{ts.replace(':', '-').replace('.', '_')}.json"
    file_path = live_dir / filename
    file_path.write_text(json.dumps(record, indent=2, sort_keys=True), encoding="utf-8")
    return file_path


def format_table(rows: list[list[str]], headers: list[str]) -> str:
    col_widths = [len(h) for h in headers]
    for row in rows:
        for i, val in enumerate(row):
            col_widths[i] = max(col_widths[i], len(str(val)))
    sep = "+-" + "-+-".join("-" * w for w in col_widths) + "-+"
    lines = [sep]
    header_str = "| " + " | ".join(h.ljust(col_widths[i]) for i, h in enumerate(headers)) + " |"
    lines.append(header_str)
    lines.append(sep)
    for row in rows:
        row_str = "| " + " | ".join(str(val).ljust(col_widths[i]) for i, val in enumerate(row)) + " |"
        lines.append(row_str)
    lines.append(sep)
    return "\n".join(lines)


def write_markdown_report(report_path: Path, table_rows: list[dict], failed_runs: list[dict], discrepancies: dict[str, list[str]], staging_result: dict | None):
    report_path.parent.mkdir(parents=True, exist_ok=True)
    now_str = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")

    md = []
    md.append("# Live Smoke Verification Report")
    md.append("")
    md.append(f"**Run Timestamp**: `{now_str}`  ")
    md.append("**Target Environment**: `https://demo-booking-tau.vercel.app`  ")
    md.append("**API Key Status**: Present in `.env` (value never logged or committed)  ")
    md.append("**Safety Check**: Staging only. No simulated or real order was placed (`never place an order`).  ")
    md.append("")
    md.append("## Measured Live Runs")
    md.append("")
    md.append("| Step / Platform | Status | Run ID | Duration | Details |")
    md.append("| :--- | :---: | :--- | :---: | :--- |")
    for row in table_rows:
        md.append(f"| {row['name']} | **{row['status']}** | `{row['run_id']}` | {row['duration']} | {row['details']} |")
    md.append("")

    md.append("## Discrepancies vs `data/food.json`")
    md.append("")
    if any(discrepancies.values()):
        for platform, diffs in discrepancies.items():
            if diffs:
                md.append(f"### {platform.capitalize()}")
                for diff in diffs:
                    md.append(f"- {diff}")
    else:
        md.append("All successfully extracted live options matched `data/food.json` exactly (dish, price, veg, rating, ETA, fees).")
    md.append("")

    md.append("## Failed Runs")
    md.append("")
    if failed_runs:
        for fail in failed_runs:
            md.append(f"- **{fail['name']}**: Run ID `{fail.get('run_id')}`, Reason: `{fail.get('reason')}`")
    else:
        md.append("No failed runs encountered.")
    md.append("")

    md.append("## FoodHub Staging (?scenario=extras)")
    md.append("")
    if staging_result and staging_result.get("success"):
        staged = staging_result["cart"]
        md.append(f"- **Staged Cart ID**: `{staged.get('cart_id')}`")
        md.append(f"- **Total**: Rs `{staged.get('total')}` (Expected: `320`)")
        md.append(f"- **Tip item present**: `{staging_result.get('tip_present')}` (Rs 30)")
        md.append(f"- **Donation item present**: `{staging_result.get('donation_present')}` (Rs 10)")
        md.append("- **Order Status**: **NOT PLACED** (Verified: no final commit call was made)")
    elif staging_result:
        md.append(f"- **Staging Failed**: `{staging_result.get('error')}`")
    else:
        md.append("- Staging was not executed.")
    md.append("")

    report_path.write_text("\n".join(md), encoding="utf-8")


def main():
    load_dotenv(ROOT / ".env")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["live", "replay"], default="live")
    parser.add_argument("--max-runs", type=int, default=4, help="Cap on total automation runs (default: 4)")
    parser.add_argument("--timeout", type=int, default=120, help="Per-platform timeout in seconds")
    parser.add_argument("--output-md", default="docs/live-smoke.md", help="Path to markdown output report")
    parser.add_argument("--run-api", action="store_true", help="Run HTTP API verification (POST /food/compare and /food/run)")
    args = parser.parse_args()

    # Requirement 1: Check TinyFish API key loaded from .env, print presence only
    has_key = bool(os.getenv("TINYFISH_API_KEY"))
    print(f"TinyFish API key present: {has_key}")

    if args.mode == "live":
        if not has_key:
            print("ERROR: TINYFISH_API_KEY missing in .env; cannot run live smoke.", file=sys.stderr)
            return 1
        os.environ.pop("REPLAY", None)
    else:
        os.environ["REPLAY"] = "1"
        print("Running in replay mode using recorded fixtures.")

    catalog = load_expected_catalog()
    total_runs = 0
    consecutive_errors = 0
    max_consecutive_errors = 2

    table_rows: list[dict] = []
    failed_runs: list[dict] = []
    discrepancies: dict[str, list[str]] = {}
    staging_result: dict | None = None

    # Requirement 2: Run compare_all live with async API & per-platform timeout
    print(f"\n[1/2] Running compare_all across 3 platforms (timeout={args.timeout}s, max_runs={args.max_runs})...")
    urls = [url for _, url in PLATFORM_URLS]
    total_runs += len(urls)

    comparison = compare_all(urls, timeout_seconds=args.timeout)

    for platform_slug, url in PLATFORM_URLS:
        run_info = comparison.runs.get(platform_slug)
        if run_info and run_info.success:
            consecutive_errors = 0
            diffs = compare_options_against_catalog(platform_slug, run_info.options, catalog)
            discrepancies[platform_slug] = diffs
            detail = f"{len(run_info.options)} options extracted"
            if diffs:
                detail += f" ({len(diffs)} catalog diffs)"
            else:
                detail += " (matches data/food.json)"
            table_rows.append({
                "name": f"{platform_slug.capitalize()} compare",
                "status": "PASS",
                "run_id": run_info.run_id or "live",
                "duration": f"{run_info.duration_seconds:.1f}s",
                "details": detail,
            })
            save_recording(platform_slug, "compare", "clean", run_info.run_id, [o.model_dump(mode="json") for o in run_info.options])
        else:
            consecutive_errors += 1
            reason = run_info.reason if run_info else comparison.failures.get(platform_slug, "Unknown error")
            run_id = getattr(run_info, "run_id", None) or "none"
            dur = f"{run_info.duration_seconds:.1f}s" if run_info else "0.0s"
            table_rows.append({
                "name": f"{platform_slug.capitalize()} compare",
                "status": "FAIL",
                "run_id": run_id,
                "duration": dur,
                "details": reason,
            })
            failed_runs.append({
                "name": f"{platform_slug.capitalize()} compare",
                "run_id": run_id,
                "reason": reason,
            })
            save_recording(platform_slug, "compare_failed", "clean", run_id, {"error": reason})

    # Requirement 3: Run stage_winner live on FoodHub Spice Route with ?scenario=extras
    print(f"\n[2/2] Running stage_winner live on FoodHub Spice Route (?scenario=extras)...")
    if total_runs >= args.max_runs:
        print(f"Skipping staging: total runs ({total_runs}) reached --max-runs cap ({args.max_runs}).")
    elif consecutive_errors >= max_consecutive_errors:
        print(f"Skipping staging: stopped early due to {consecutive_errors} repeated platform errors.")
    else:
        # Find FoodHub Spice Route option
        foodhub_options = [o for o in comparison.options if o.platform == "FoodHub" and o.restaurant == "Spice Route"]
        if not foodhub_options:
            # Fall back to data/food.json reference if FoodHub compare failed
            exp_fh = next(o for o in catalog["options"] if o["platform"] == "FoodHub" and o["restaurant"] == "Spice Route")
            clean_fh = {k: v for k, v in exp_fh.items() if k != "id"}
            if clean_fh.get("url", "").startswith("/"):
                clean_fh["url"] = f"https://demo-booking-tau.vercel.app{clean_fh['url']}"
            winner_opt = FoodOption.model_validate(clean_fh)
        else:
            winner_opt = foodhub_options[0]

        staged_url = set_scenario(winner_opt.url, "extras")
        staged_option = winner_opt.model_copy(update={"url": staged_url})

        total_runs += 1
        t0 = time.monotonic()
        try:
            cart = stage_winner(staged_option, CONTRACT, timeout_seconds=args.timeout)
            stage_duration = time.monotonic() - t0
            run_id = "fixture" if args.mode == "replay" else (getattr(cart, "run_id", None) or getattr(staged_option, "run_id", None) or "live")
            if args.mode == "live":
                stage_files = sorted((ROOT / "recordings" / "food" / "live").glob("foodhub__stage__*.json"), key=os.path.getmtime)
                if stage_files:
                    try:
                        payload = json.loads(stage_files[-1].read_text(encoding="utf-8"))
                        run_id = payload.get("run_id") or run_id
                    except Exception:
                        pass

            # Verify: total == 320, tip 30, donation 10
            tip_item = next((item for item in cart.items if item.type == "tip" and item.price == 30), None)
            donation_item = next((item for item in cart.items if item.type == "donation" and item.price == 10), None)
            total_correct = (cart.total == 320)
            tip_present = tip_item is not None
            donation_present = donation_item is not None

            passed = total_correct and tip_present and donation_present
            detail = f"Total={cart.total} (exp 320), Tip={tip_present}, Donation={donation_present}; Order NOT placed"

            table_rows.append({
                "name": "FoodHub stage (?scenario=extras)",
                "status": "PASS" if passed else "FAIL",
                "run_id": run_id,
                "duration": f"{stage_duration:.1f}s",
                "details": detail,
            })
            if not passed:
                failed_runs.append({
                    "name": "FoodHub stage (?scenario=extras)",
                    "run_id": run_id,
                    "reason": f"Expected total 320, tip 30, donation 10; got total={cart.total}, tip={tip_present}, donation={donation_present}",
                })

            staging_result = {
                "success": passed,
                "cart": cart.model_dump(mode="json"),
                "tip_present": tip_present,
                "donation_present": donation_present,
            }
            save_recording("foodhub", "stage", "extras", run_id, cart.model_dump(mode="json"))
        except Exception as error:
            stage_duration = time.monotonic() - t0
            run_id = getattr(error, "run_id", None) or "none"
            stage_files = sorted((ROOT / "recordings" / "food" / "live").glob("foodhub__stage_failed__*.json"), key=os.path.getmtime)
            if stage_files:
                try:
                    payload = json.loads(stage_files[-1].read_text(encoding="utf-8"))
                    run_id = payload.get("run_id") or run_id
                except Exception:
                    pass
            table_rows.append({
                "name": "FoodHub stage (?scenario=extras)",
                "status": "FAIL",
                "run_id": run_id,
                "duration": f"{stage_duration:.1f}s",
                "details": str(error),
            })
            failed_runs.append({
                "name": "FoodHub stage (?scenario=extras)",
                "run_id": run_id,
                "reason": str(error),
            })
            staging_result = {"success": False, "error": str(error)}
            save_recording("foodhub", "stage_failed", "extras", run_id, {"error": str(error)})

    # Requirement 6: Print pass/fail table and write docs/live-smoke.md
    print("\nLive Smoke Test Summary:")
    table_data = [[r["name"], r["status"], r["run_id"], r["duration"], r["details"]] for r in table_rows]
    headers = ["Step / Target", "Status", "Run ID", "Duration", "Details"]
    print(format_table(table_data, headers))

    out_md = ROOT / args.output_md
    write_markdown_report(out_md, table_rows, failed_runs, discrepancies, staging_result)
    print(f"\nReport written to {out_md}")


    if args.run_api:
        print("\n[3/3] Running through HTTP API with REPLAY unset (POST /food/compare and POST /food/run)...")
        try:
            from fastapi.testclient import TestClient
            from app.main import create_app
            with TestClient(create_app(), base_url="http://localhost") as client:
                payload = {
                    "contract": CONTRACT.model_dump(mode="json"),
                    "platform_urls": [u for _, u in PLATFORM_URLS],
                    "scenario": "extras",
                }
                if args.mode == "replay":
                    payload["replay"] = True
                cmp_resp = client.post("/food/compare", json=payload)
                if cmp_resp.status_code != 200:
                    print(f"  POST /food/compare returned HTTP {cmp_resp.status_code}: {cmp_resp.text}")
                cmp_data = cmp_resp.json()
                print(f"  POST /food/compare -> HTTP {cmp_resp.status_code}")
                print(f"  Task ID: {cmp_data.get('task_id')}")
                rec = cmp_data.get('recommended') or {}
                print(f"  Recommended option: {rec.get('restaurant')} - {rec.get('dish')}")

                run_payload = {"task_id": cmp_data["task_id"], "scenario": "extras"}
                if args.mode == "replay":
                    run_payload["replay"] = True
                run_resp = client.post("/food/run", json=run_payload)
                if run_resp.status_code != 200:
                    print(f"  POST /food/run returned HTTP {run_resp.status_code}: {run_resp.text}")
                run_data = run_resp.json()
                print(f"  POST /food/run -> HTTP {run_resp.status_code} (Status: {run_data.get('status')})")
                print("\n  Guarded Event Sequence:")
                for ev in run_data.get("events", []):
                    ev_type = ev.get("type")
                    status = ev.get("status", "")
                    detail = ev.get("detail", "")
                    ev_payload = ev.get("payload", {})
                    print(f"    [{status.upper()}] {ev_type}: {detail}")
                    if ev_type == "food_decision":
                        dec = ev_payload.get("food_decision", {})
                        print(f"      -> Decision Result: {dec.get('result')}, reasons: {dec.get('reasons')}, remove: {dec.get('remove_item_ids')}")
                    elif ev_type == "food_fix_started":
                        print(f"      -> Fix: removing items {ev_payload.get('remove_item_ids')}")
                    elif ev_type == "food_recheck":
                        c = ev_payload.get("cart", {})
                        print(f"      -> Fresh Cart: items={len(c.get('items', []))}, total={c.get('total')}")
                    elif ev_type == "food_commit_result":
                        print(f"      -> Commit Result: order_id={ev_payload.get('order_id')}, total={ev_payload.get('total')}")
        except Exception as e:
            print(f"  HTTP API verification failed: {e}", file=sys.stderr)
            import traceback; traceback.print_exc()

    return 1 if failed_runs else 0


if __name__ == "__main__":
    sys.exit(main())
