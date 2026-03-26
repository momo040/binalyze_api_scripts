import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib.runtime import OUTPUT_DIR, display_id, load_api_context


api_get = None
api_post = None
paginate_get = None


def parse_args(argv):
    parser = argparse.ArgumentParser(
        description=(
            "Show evidence structure for an investigation, including endpoints, tasks, "
            "and Investigation Hub data when available."
        )
    )
    parser.add_argument("investigation_id", help="Investigation ID")
    parser.add_argument("org_id", nargs="?", help="Optional organization ID")
    return parser.parse_args(argv)


def try_investigation_hub(air_host, api_token, investigation_id):
    """Try Investigation Hub API endpoints (available on some tenant tiers)."""
    results = {}

    base = f"/api/public/investigation-hub/investigations/{investigation_id}"

    resp = api_get(air_host, api_token, f"{base}/evidence/data-structure")
    if resp.ok:
        results["dataStructure"] = resp.json()

    resp = api_get(air_host, api_token, f"{base}/assets")
    if resp.ok:
        results["assets"] = resp.json()

    resp = api_get(air_host, api_token, f"{base}/evidence/counts")
    if resp.ok:
        results["evidenceCounts"] = resp.json()

    resp = api_get(air_host, api_token, f"{base}/findings/data-structure")
    if resp.ok:
        results["findingsStructure"] = resp.json()

    resp = api_post(air_host, api_token, f"{base}/findings/summary", {})
    if resp.ok:
        results["findingsSummary"] = resp.json()

    return results if results else None


def get_case_by_investigation_id(air_host, api_token, investigation_id, org_id=None):
    """Find the case associated with this investigation ID."""
    if org_id:
        org_ids_to_search = [org_id]
    else:
        orgs = paginate_get(
            air_host, api_token, "/api/public/organizations", verbose=False
        )
        org_ids_to_search = [
            org.get("_id") or org.get("id") or org.get("organizationId")
            for org in orgs
        ]
        org_ids_to_search = [value for value in org_ids_to_search if value]

    for current_org_id in org_ids_to_search:
        params = {"filter[organizationIds]": current_org_id}
        cases = paginate_get(
            air_host, api_token, "/api/public/cases", params=params, verbose=False
        )
        for case in cases:
            metadata = case.get("metadata") or {}
            if metadata.get("investigationId") == investigation_id:
                return case

    return None


def _format_size(size):
    if size > 1024 * 1024:
        return f"{size / (1024 * 1024):.1f} MB"
    if size > 1024:
        return f"{size / 1024:.1f} KB"
    return f"{size} bytes"


def get_case_endpoints(air_host, api_token, case_id, org_id):
    params = {
        "filter[organizationIds]": org_id,
        "pageNumber": 1,
        "pageSize": 100,
    }
    resp = api_get(air_host, api_token, f"/api/public/cases/{case_id}/endpoints", params)
    if not resp.ok:
        return []
    return resp.json().get("result", {}).get("entities", [])


def display_results(case, tasks, endpoints, hub_results):
    print(f"\n{'='*80}")
    print("EVIDENCE STRUCTURE REPORT")
    print(f"{'='*80}\n")

    case_id = case.get("_id", "N/A")
    name = case.get("name", "N/A")
    status = case.get("status", "N/A")
    org_id = case.get("organizationId", "N/A")
    metadata = case.get("metadata", {})
    investigation_id = display_id(metadata.get("investigationId"))
    disk_usage = metadata.get("diskUsageInBytes", 0)

    print(f"Case: {name} ({case_id})")
    print(f"Status: {status}")
    print(f"Organization ID: {org_id}")
    print(f"Investigation ID: {investigation_id}")
    if disk_usage:
        print(f"Disk Usage: {disk_usage / (1024 * 1024):.1f} MB")

    category = case.get("category", {})
    if category:
        print(f"Category: {category.get('name', 'N/A')}")

    if hub_results:
        print(f"\n{'─'*80}")
        print("INVESTIGATION HUB DATA (from API)")
        print(f"{'─'*80}\n")

        for key, label in [
            ("dataStructure", "Evidence Data Structure"),
            ("findingsStructure", "Findings Data Structure"),
            ("findingsSummary", "Findings Summary"),
            ("evidenceCounts", "Evidence Counts"),
            ("assets", "Investigation Assets"),
        ]:
            if key in hub_results:
                result = hub_results[key].get("result", hub_results[key])
                print(f"  {label}:")
                print(f"  {json.dumps(result, indent=4)[:2000]}")
                print()

    print(f"\n{'─'*80}")
    print(f"ENDPOINTS ({len(endpoints)})")
    print(f"{'─'*80}\n")

    for endpoint in endpoints:
        print(f"  {endpoint.get('name', 'Unknown')}")
        print(f"    ID: {endpoint.get('_id', 'N/A')}")
        print(f"    OS: {endpoint.get('os', 'N/A')} ({endpoint.get('platform', 'N/A')})")
        print(f"    IP: {endpoint.get('ipAddress', 'N/A')}")
        print()

    acquisitions = [task for task in tasks if task.get("type") == "acquisition"]
    triages = [task for task in tasks if task.get("type") == "triage"]
    others = [task for task in tasks if task.get("type") not in ["acquisition", "triage"]]

    print(f"{'─'*80}")
    print(f"EVIDENCE COLLECTED ({len(tasks)} task(s))")
    print(f"{'─'*80}\n")

    for task_group, label in [
        (acquisitions, "Acquisitions"),
        (triages, "Triage"),
        (others, "Other"),
    ]:
        if not task_group:
            continue

        print(f"  {label} ({len(task_group)}):")
        print()

        for task in task_group:
            task_name = task.get("name", "Unnamed")
            task_type = task.get("displayType") or task.get("type", "N/A")
            endpoint_name = task.get("endpointName", "N/A")
            status = task.get("status", "N/A")
            task_id = task.get("taskId", "N/A")
            task_metadata = task.get("metadata", {})

            print(f"    [{task_name}]")
            print(f"      Task ID: {task_id}")
            print(f"      Type: {task_type}")
            print(f"      Endpoint: {endpoint_name}")
            print(f"      Status: {status}")

            has_case_db = task_metadata.get("hasCaseDb", False)
            has_drone = task_metadata.get("hasDroneData", False)
            case_ppc_entries = task_metadata.get("casePpcEntries", [])
            drone_entries = task_metadata.get("droneZipEntries", [])
            investigation_info = task_metadata.get("investigation", {})
            acquisition_profile = task_metadata.get("acquisitionProfile", {})

            if acquisition_profile:
                print(
                    f"      Profile: {acquisition_profile.get('name', acquisition_profile.get('id', 'N/A'))}"
                )

            print(f"      Has Case.db: {has_case_db}")
            print(f"      Has DRONE Data: {has_drone}")

            if investigation_info:
                investigation_status = investigation_info.get("status", "N/A")
                investigation_disk = investigation_info.get("diskUsageInBytes", 0)
                print(f"      Investigation Status: {investigation_status}")
                if investigation_disk:
                    print(
                        f"      Investigation Disk Usage: {investigation_disk / (1024 * 1024):.1f} MB"
                    )

            if case_ppc_entries:
                print("      Evidence Files:")
                for entry in case_ppc_entries:
                    print(
                        f"        - {entry.get('name', '?')} ({_format_size(entry.get('size', 0))})"
                    )

            if drone_entries:
                print("      DRONE Files:")
                for entry in drone_entries:
                    print(
                        f"        - {entry.get('name', '?')} ({_format_size(entry.get('size', 0))})"
                    )

            response = task.get("response", {})
            if response:
                match_count = response.get("matchCount")
                if match_count is not None:
                    print(f"      Match Count: {match_count}")

            print()


def main():
    global api_get, api_post, paginate_get

    args = parse_args(sys.argv[1:])

    try:
        (
            air_host,
            api_token,
            runtime_api_get,
            runtime_api_post,
            runtime_paginate_get,
        ) = load_api_context()
        api_get = runtime_api_get
        api_post = runtime_api_post
        paginate_get = runtime_paginate_get

        print("Trying Investigation Hub API endpoints...", flush=True)
        hub_results = try_investigation_hub(air_host, api_token, args.investigation_id)
        if hub_results:
            print(
                f"  Investigation Hub API available ({len(hub_results)} endpoint(s) returned data)"
            )
        else:
            print("  Investigation Hub API not available on this tenant, using fallback.")

        print("Looking up case for this investigation...", flush=True)
        case = get_case_by_investigation_id(
            air_host, api_token, args.investigation_id, args.org_id
        )

        if not case:
            print(
                f"\nError: Could not find a case with investigation ID: {args.investigation_id}",
                file=sys.stderr,
            )
            sys.exit(1)

        case_id = case.get("_id")
        case_org_id = case.get("organizationId")
        print(f"  Found case: {case.get('name')} ({case_id})")

        print("Fetching case tasks...", flush=True)
        tasks = paginate_get(
            air_host, api_token, f"/api/public/cases/{case_id}/tasks", verbose=False
        )
        print(f"  Found {len(tasks)} task(s)")

        print("Fetching case endpoints...", flush=True)
        endpoints = get_case_endpoints(air_host, api_token, case_id, case_org_id)
        print(f"  Found {len(endpoints)} endpoint(s)")

        display_results(case, tasks, endpoints, hub_results)

        os.makedirs(OUTPUT_DIR, exist_ok=True)
        filename = os.path.join(
            OUTPUT_DIR, f"evidence_structure_{args.investigation_id[:8]}.json"
        )
        output = {
            "investigationId": args.investigation_id,
            "case": case,
            "tasks": tasks,
            "endpoints": endpoints,
        }
        if hub_results:
            output["investigationHub"] = hub_results

        with open(filename, "w", encoding="utf-8") as handle:
            json.dump(output, handle, indent=2, ensure_ascii=False)

        print(f"\nRaw data saved to: {filename}\n")
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
