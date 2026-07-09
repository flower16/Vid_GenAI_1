"""
Report the status of every external integration from the CLI.

Snowflake, LangSmith, Fireworks, Azure AD, Pinecone — shows which are configured
(keys present in backend/.env) and, with --live, whether each is reachable now.

Usage (from backend/):
    python scripts/check_integrations.py            # configured / not-configured
    python scripts/check_integrations.py --live     # also ping each configured service
    python scripts/check_integrations.py --json
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from app.core.integrations import integration_report  # noqa: E402


def _mark(configured: bool, reachable) -> str:
    if not configured:
        return "· not configured"
    if reachable is None:
        return "✓ configured"
    return "✓ reachable" if reachable else "✗ unreachable"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", action="store_true", help="ping each configured service")
    ap.add_argument("--json", action="store_true", help="emit JSON")
    args = ap.parse_args()

    report = integration_report(live=args.live)
    if args.json:
        print(json.dumps(report, indent=2))
        return 0

    print(f"Integrations — environment={report['environment']}, "
          f"live_checked={report['live_checked']}, "
          f"configured={report['configured_count']}/{len(report['integrations'])}\n")
    for s in report["integrations"]:
        print(f"  {s['name']:<11} {_mark(s['configured'], s['reachable']):<16} {s['detail']}")

    # Non-zero exit if a live check found a configured-but-unreachable service.
    broken = [s for s in report["integrations"] if s["reachable"] is False]
    if broken:
        print(f"\n{len(broken)} configured integration(s) unreachable.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
