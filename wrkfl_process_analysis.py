"""
Workflow: Windows Process Analysis

Interactive workflow that:
  1. Loads org from .env (BINALYZE_ORG_ID)
  2. Lists open cases and lets you pick one
  3. Downloads all Windows process data to SQLite (streaming)
  4. Prints summary, top-10 and bottom-10 processes by frequency
"""

import argparse
import os
import sqlite3
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from lib.runtime import load_api_context
from scripts.case_download_evidence import (
    OUTPUT_DIR,
    build_endpoint_name_map,
    get_assets,
    stream_evidence_data,
)


PLATFORM = "windows"
EVIDENCE_CATEGORY = "processes"
paginate_get = None


def parse_args(argv):
    parser = argparse.ArgumentParser(
        description=(
            "Interactive workflow that downloads Windows process evidence for a case "
            "and prints top/bottom process frequency analysis."
        )
    )
    return parser.parse_args(argv)


def load_org_id():
    org_id = os.getenv("BINALYZE_ORG_ID")
    if not org_id:
        raise RuntimeError("Set BINALYZE_ORG_ID in .env")
    return org_id


def fetch_open_cases(air_host, api_token, org_id):
    params = {
        "filter[organizationIds]": org_id,
        "filter[status]": "open",
    }
    return paginate_get(
        air_host, api_token, "/api/public/cases", params=params, verbose=False
    )


def select_case(cases):
    """Display interactive menu and return the selected case dict."""
    if not cases:
        print("No open cases found for this organization.")
        sys.exit(0)

    print(f"\n{'='*70}")
    print("OPEN CASES")
    print(f"{'='*70}\n")

    for index, case in enumerate(cases, 1):
        name = case.get("name") or case.get("title") or "(untitled)"
        owner = case.get("owner") or "?"
        created = (case.get("createdAt") or "")[:10]
        metadata = case.get("metadata") or {}
        investigation_id = metadata.get("investigationId") or "none"

        print(f"  [{index:>3}]  {name}")
        print(
            f"         Owner: {owner}  |  Created: {created}  |  Investigation: {investigation_id}"
        )

    print()
    while True:
        try:
            choice = input(f"Select case [1-{len(cases)}]: ").strip()
            case_index = int(choice) - 1
            if 0 <= case_index < len(cases):
                return cases[case_index]
            print(f"  Enter a number between 1 and {len(cases)}.")
        except (ValueError, EOFError):
            print(f"  Enter a number between 1 and {len(cases)}.")


def get_assignment_ids(assets_data, platform):
    """Extract assignment IDs for a given platform from assets data."""
    assignment_ids = []
    for platform_group in assets_data:
        if platform_group.get("platform") != platform:
            continue
        for asset in platform_group.get("assets", []):
            for task in asset.get("tasks", []):
                assignment_id = task.get("_id")
                if assignment_id:
                    assignment_ids.append(assignment_id)
    return assignment_ids


def print_analysis(db_path, table_name):
    """Query SQLite and print summary + frequency analysis."""
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    total = cur.execute(f'SELECT COUNT(*) FROM "{table_name}"').fetchone()[0]
    endpoints = cur.execute(
        f'SELECT COUNT(DISTINCT air_endpoint_name) FROM "{table_name}"'
    ).fetchone()[0]
    columns = [
        row[1] for row in cur.execute(f'PRAGMA table_info("{table_name}")').fetchall()
    ]

    print(f"\n{'='*70}")
    print("PROCESS ANALYSIS SUMMARY")
    print(f"{'='*70}\n")
    print(f"  Table:      {table_name}")
    print(f"  Database:   {db_path}")
    print(f"  Total rows: {total:,}")
    print(f"  Endpoints:  {endpoints}")
    print(f"  Columns:    {len(columns)}")

    print(f"\n  {'─'*66}")
    print("  TOP 10 PROCESSES (highest frequency)")
    print(f"  {'─'*66}\n")
    print(f"  {'#':<5} {'Process Name':<45} {'Count':>8} {'%':>7}")
    print(f"  {'─'*5} {'─'*45} {'─'*8} {'─'*7}")

    top10 = cur.execute(
        f'SELECT name, COUNT(*) as cnt FROM "{table_name}" '
        f'GROUP BY name ORDER BY cnt DESC LIMIT 10'
    ).fetchall()

    for index, (name, count) in enumerate(top10, 1):
        pct = (count / total * 100) if total else 0
        display_name = (name or "(empty)")[:45]
        print(f"  {index:<5} {display_name:<45} {count:>8,} {pct:>6.1f}%")

    print(f"\n  {'─'*66}")
    print("  BOTTOM 10 PROCESSES (lowest frequency)")
    print(f"  {'─'*66}\n")
    print(f"  {'#':<5} {'Process Name':<45} {'Count':>8} {'%':>7}")
    print(f"  {'─'*5} {'─'*45} {'─'*8} {'─'*7}")

    bottom10 = cur.execute(
        f'SELECT name, COUNT(*) as cnt FROM "{table_name}" '
        f'GROUP BY name ORDER BY cnt ASC LIMIT 10'
    ).fetchall()

    for index, (name, count) in enumerate(bottom10, 1):
        pct = (count / total * 100) if total else 0
        display_name = (name or "(empty)")[:45]
        print(f"  {index:<5} {display_name:<45} {count:>8,} {pct:>6.1f}%")

    unique = cur.execute(
        f'SELECT COUNT(DISTINCT name) FROM "{table_name}"'
    ).fetchone()[0]
    print(f"\n  Unique process names: {unique:,}")

    conn.close()


def main():
    global paginate_get

    parse_args(sys.argv[1:])

    try:
        air_host, api_token, _, _, runtime_paginate_get = load_api_context()
        paginate_get = runtime_paginate_get
        org_id = load_org_id()

        print("Binalyze AIR Process Analysis Workflow")
        print(f"  Host: {air_host}")
        print(f"  Org:  {org_id}")

        print("\nFetching open cases...", flush=True)
        cases = fetch_open_cases(air_host, api_token, org_id)
        selected = select_case(cases)

        case_name = selected.get("name") or selected.get("title") or "unknown"
        metadata = selected.get("metadata") or {}
        investigation_id = metadata.get("investigationId")

        if not investigation_id:
            print("\nError: Selected case has no investigationId.", file=sys.stderr)
            print("This case may not have completed acquisition yet.", file=sys.stderr)
            sys.exit(1)

        print(f"\n  Selected: {case_name}")
        print(f"  Investigation ID: {investigation_id}")

        print("\nFetching investigation assets...", flush=True)
        assets_data = get_assets(air_host, api_token, investigation_id)
        if not assets_data:
            print("Error: Could not retrieve investigation assets.", file=sys.stderr)
            sys.exit(1)

        assignment_ids = get_assignment_ids(assets_data, PLATFORM)
        if not assignment_ids:
            all_platforms = [pg.get("platform") for pg in assets_data]
            print("Error: No Windows assets found.", file=sys.stderr)
            print(f"Available platforms: {', '.join(all_platforms)}", file=sys.stderr)
            sys.exit(1)

        endpoint_name_map = build_endpoint_name_map(assets_data)
        print(f"  Found {len(assignment_ids)} Windows endpoint(s)")

        os.makedirs(OUTPUT_DIR, exist_ok=True)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        safe_case = case_name.replace(" ", "_").replace("/", "_").replace("\\", "_")[:30]
        table_name = f"processes_{safe_case}_{timestamp}"
        db_path = os.path.join(OUTPUT_DIR, "evidence.db")

        print("\nDownloading Windows processes...", flush=True)
        print(f"  Table: {table_name}")

        writer, downloaded, _ = stream_evidence_data(
            air_host,
            api_token,
            investigation_id,
            PLATFORM,
            EVIDENCE_CATEGORY,
            assignment_ids,
            endpoint_name_map,
            db_path,
            page_size=500,
            request_delay=0.1,
            table_name=table_name,
        )

        if downloaded == 0:
            writer.close()
            print("\n  No process data found for this case.")
            sys.exit(0)

        writer.close()

        print_analysis(db_path, table_name)
        print("\nDone.\n")
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
