"""Verify Parent readiness, streamed child freshness and the local HTTP fixtures."""

import argparse
import json
from pathlib import Path
import sys
import time
import urllib.error
import urllib.parse
import urllib.request


def fetch(url):
    with urllib.request.urlopen(url, timeout=5) as response:
        payload = response.read(8 * 1024 * 1024 + 1)
    if len(payload) > 8 * 1024 * 1024:
        raise ValueError("Parent response exceeds the inventory limit")
    data = json.loads(payload)
    if not isinstance(data, dict):
        raise ValueError("Invalid Parent response")
    return data


def verify(url, require_child=False, verify_fixtures=False):
    base = url.rstrip("/")
    info = fetch(base + "/api/v1/info")
    if not isinstance(info.get("version"), str):
        raise ValueError("Invalid Parent API version")
    children = [
        host
        for host in info.get("mirrored_hosts_status", [])
        if host.get("hops", 0) > 0 and host.get("reachable")
    ]
    count = info.get("hosts-available")
    mirrored_hosts = info.get("mirrored_hosts_status", [])
    report = {
        "checked_at_unix": int(time.time()),
        "api_status": "ready",
        "version": info["version"],
        "hosts_available": count if type(count) is int else None,
        "reachable_children": len(children),
        "streamed_child_verified": False,
    }
    if require_child or verify_fixtures:
        if len(children) != 1:
            observed = [
                {
                    "hostname": host.get("hostname"),
                    "guid": host.get("guid"),
                    "hops": host.get("hops"),
                    "reachable": host.get("reachable"),
                }
                for host in mirrored_hosts
                if isinstance(host, dict)
            ]
            raise ValueError(
                "This one-Mac pilot expects exactly one reachable child; "
                f"observed {len(children)} reachable children from {len(observed)} mirrored hosts: "
                f"{json.dumps(observed, separators=(',', ':'))}"
            )
        child = base + "/host/" + urllib.parse.quote(children[0]["guid"], safe="")
        charts = fetch(child + "/api/v1/charts").get("charts", {})
        network_charts = [c for c in charts.values() if c.get("context", "").startswith("net.")]
        fresh = [c for c in network_charts if 0 <= time.time() - c.get("last_entry", 0) <= 120]
        if not fresh:
            raise ValueError("Child has no fresh network observations")
        report.update(
            {
                "streamed_child_verified": True,
                "child_charts": len(charts),
                "fresh_network_charts": len(fresh),
            }
        )
        if verify_fixtures:
            fixtures = {}
            for name in ("healthy", "slow", "unavailable"):
                values = {}
                for suffix in ("response_time", "request_status"):
                    identifier = f"httpcheck_pilot_fixture_{name}.{suffix}"
                    chart = charts.get(identifier, {})
                    if not 0 <= time.time() - chart.get("last_entry", 0) <= 120:
                        raise ValueError("Fixture evidence is missing or stale")
                    query = urllib.parse.urlencode(
                        {"chart": identifier, "after": -30, "points": 1, "group": "average"}
                    )
                    data = fetch(child + "/api/v1/data?" + query)
                    rows = data.get("data", [])
                    if not rows:
                        raise ValueError("Fixture has no samples")
                    dimensions = dict(zip(data["labels"][1:], rows[0][1:]))
                    if any(value is None for value in dimensions.values()):
                        raise ValueError("Fixture sample is incomplete")
                    if suffix == "response_time":
                        values["response_ms"] = dimensions["time"]
                    else:
                        values["success"] = dimensions["success"]
                        values["bad_status"] = dimensions["bad_status"]
                fixtures[name] = values
            if (
                fixtures["healthy"]["success"] < 0.9
                or fixtures["slow"]["success"] < 0.9
                or fixtures["unavailable"]["bad_status"] < 0.9
                or fixtures["slow"]["response_ms"] < fixtures["healthy"]["response_ms"] + 500
            ):
                raise ValueError("Fixture outcomes do not match the controlled scenarios")
            report.update({"fixture_results": fixtures, "fixtures_verified": True})
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:19998")
    parser.add_argument("--require-child", action="store_true")
    parser.add_argument("--verify-fixtures", action="store_true")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--wait-seconds", type=int, default=0)
    args = parser.parse_args()
    if not 0 <= args.wait_seconds <= 180:
        parser.error("--wait-seconds must be between 0 and 180")
    deadline = time.monotonic() + args.wait_seconds
    print(
        f"Checking Parent {args.url.rstrip('/')} "
        f"(child_required={args.require_child}, fixtures={args.verify_fixtures})",
        file=sys.stderr,
        flush=True,
    )
    while True:
        try:
            report = verify(args.url, args.require_child, args.verify_fixtures)
            break
        except (OSError, ValueError, KeyError, TypeError, urllib.error.URLError) as exc:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                parser.exit(1, f"Parent verification failed ({type(exc).__name__}): {exc}\n")
            print(
                f"Waiting for Parent readiness ({type(exc).__name__}: {exc}); "
                f"retrying for at most {int(remaining)}s",
                file=sys.stderr,
                flush=True,
            )
            time.sleep(min(3, remaining))
    text = json.dumps(report, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text)
    print(text, end="")


if __name__ == "__main__":
    main()
