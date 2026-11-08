#!/usr/bin/env python3
"""
scripts/generate_dashboard_inventory.py

Extracts and documents all 25 active Grafana dashboards in Nawari.
Generates docs/dashboards/dashboard-inventory.md with complete metadata.
"""

import json
from pathlib import Path

def main():
    root = Path(__file__).resolve().parent.parent
    inv_file = root / "docs/dashboards/raw_inventory.json"
    if not inv_file.is_file():
        print("raw_inventory.json not found!")
        return

    with open(inv_file) as f:
        inventory = json.load(f)

    lines = []
    lines.append("# Nawari Dashboard Inventory & Technical Registry")
    lines.append("")
    lines.append("**Audit Date:** 2026-11-08")
    lines.append("**Environment:** Nawari Staging Observability Platform (`mon-grafana01`)")
    lines.append(f"**Total Dashboards Audited:** {len(inventory)}")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## 1. Executive Summary of Active Dashboards")
    lines.append("")
    lines.append("| # | Dashboard Title | UID | Folder | Panels (Viz/Row) | Variables | Provisioning Source |")
    lines.append("|---|---|---|---|---|---|---|")

    for idx, d in enumerate(sorted(inventory, key=lambda x: (x["folderTitle"], x["title"])), 1):
        vars_str = ", ".join(d["variables"]) if d["variables"] else "None"
        prov = "File Provisioned" if d["provisioned"] else "Direct API"
        viz = d["viz_panels_count"]
        rows = d["rows_count"]
        tot = d["total_panels"]
        lines.append(f"| {idx} | {d['title']} | `{d['uid']}` | {d['folderTitle']} | {tot} ({viz}/{rows}) | {vars_str} | {prov} |")

    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## 2. Granular Per-Dashboard Technical Specification")
    lines.append("")

    for idx, d in enumerate(sorted(inventory, key=lambda x: (x["folderTitle"], x["title"])), 1):
        lines.append(f"### {idx}. {d['title']}")
        lines.append(f"- **UID:** `{d['uid']}`")
        lines.append(f"- **Folder:** {d['folderTitle']} (Folder UID: `{d.get('folderUid')}`)")
        lines.append(f"- **Provisioned Source:** `{d.get('disk_path', 'N/A')}`")
        lines.append(f"- **Tags:** {', '.join(d['tags']) if d['tags'] else 'None'}")
        lines.append(f"- **Variables:** {', '.join(d['variables']) if d['variables'] else 'None'}")
        lines.append(f"- **Total Panels:** {d['total_panels']} ({d['viz_panels_count']} visualization panels, {d['rows_count']} collapsible rows)")
        lines.append(f"- **Description:** {d['description'] or 'No top-level description provided'}")
        lines.append("")
        lines.append("#### Panel Inventory:")
        lines.append("| Panel ID | Title | Type | Has Description | Data Links |")
        lines.append("|---|---|---|---|---|")
        for p in d["panels"]:
            p_title = p["title"] or "(Collapsible Row Header)"
            has_desc = "Yes" if p["has_description"] else "No"
            links_count = len(p["data_links"])
            lines.append(f"| {p['id']} | {p_title} | `{p['type']}` | {has_desc} | {links_count} |")
        lines.append("")
        lines.append("---")
        lines.append("")

    out_file = root / "docs/dashboards/dashboard-inventory.md"
    out_file.write_text("\n".join(lines), encoding="utf-8")
    print(f"Successfully generated {out_file} ({len(inventory)} dashboards documented).")

if __name__ == "__main__":
    main()
