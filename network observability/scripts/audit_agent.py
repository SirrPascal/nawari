"""Read local Netdata capabilities and save a payload-free pilot inventory."""

import argparse
import json
import math
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]


def fetch_json(base_url, endpoint):
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}/api/v1/{endpoint}", headers={"Accept": "application/json"}
    )
    with urllib.request.urlopen(request, timeout=5) as response:
        # Bound the inventory response even when the selected agent is remote.
        payload = response.read(8 * 1024 * 1024 + 1)
    if len(payload) > 8 * 1024 * 1024:
        raise ValueError("Agent inventory exceeds the 8 MiB response limit")
    result = json.loads(payload)
    if not isinstance(result, dict):
        raise ValueError("Agent returned an invalid JSON inventory")
    return result


def summarize(charts, policy, now):
    """Describe chart presence and freshness without asserting service health."""
    results = []
    for check in policy["checks"]:
        matches = [
            chart
            for chart in charts.values()
            if isinstance(chart, dict)
            and (
                chart.get("context") in check.get("contexts", [])
                or (
                    check.get("context_prefix")
                    and isinstance(chart.get("context"), str)
                    and chart["context"].startswith(check["context_prefix"])
                )
            )
        ]
        ages = []
        invalid = 0
        for chart in matches:
            timestamp = chart.get("last_entry")
            if (
                isinstance(timestamp, bool)
                or not isinstance(timestamp, (int, float))
                or timestamp <= 0
                or timestamp > now + 5
                or not math.isfinite(timestamp)
            ):
                invalid += 1
            else:
                ages.append(max(0, now - timestamp))
        fresh = sum(age <= policy["freshness_seconds"] for age in ages)
        if not matches:
            status = "not_observed"
        elif fresh == len(matches):
            status = "observed_fresh"
        elif fresh:
            status = "partially_fresh"
        elif invalid:
            status = "timestamp_unknown"
        else:
            status = "observed_stale"
        results.append(
            {
                "id": check["id"],
                "scope": check["scope"],
                "status": status,
                "charts": len(matches),
                "fresh_charts": fresh,
                "invalid_timestamps": invalid,
                "oldest_valid_age_seconds": round(max(ages), 1) if ages else None,
            }
        )
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:19999")
    parser.add_argument("--output", type=Path, default=PROJECT / "evidence/agent-capabilities.json")
    args = parser.parse_args()
    policy = json.loads((PROJECT / "config/capabilities.json").read_text())
    report = {"checked_at": datetime.now(timezone.utc).isoformat(), "schema_version": 1}
    try:
        info = fetch_json(args.url, "info")
        inventory = fetch_json(args.url, "charts")
        charts = inventory.get("charts")
        if not isinstance(charts, dict):
            raise ValueError("Agent response has no charts inventory")
        report.update(
            {
                "status": "reachable",
                "agent_version": info.get("version"),
                "chart_count": len(charts),
                "freshness_seconds": policy["freshness_seconds"],
                "capabilities": summarize(charts, policy, time.time()),
            }
        )
    except (OSError, urllib.error.URLError, ValueError) as exc:
        report.update({"status": "unavailable", "error_type": type(exc).__name__})
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(f"Agent {report['status']}. Report saved to {args.output}")
    for check in report.get("capabilities", []):
        print(
            f"  {check['id']}: {check['status']} ({check['fresh_charts']}/{check['charts']} fresh charts)"
        )
    return 0 if report["status"] == "reachable" else 1


if __name__ == "__main__":
    raise SystemExit(main())
