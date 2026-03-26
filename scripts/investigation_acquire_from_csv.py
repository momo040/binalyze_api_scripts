"""
Bulk evidence acquisition for assets listed in a CSV file.

Workflow:
  1. Validate organization
  2. Resolve an existing case by case ID or investigation ID
  3. Resolve an acquisition profile
  4. Read asset identifiers from a CSV column
  5. Validate each asset against Binalyze
  6. Launch acquisition tasks only for assets that resolved cleanly
  7. Write a JSON report with matched, missing, ambiguous, and launched assets
"""

import argparse
import csv
import json
import os
import sys
import time
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib.runtime import (
    OUTPUT_DIR,
    display_id,
    is_zero_identifier,
    load_api_context,
    normalize_identifier,
    organization_display_id,
    organization_filter_id,
    organization_matches_identifier,
    unique_filterable_organization_ids,
)

DEFAULT_POLL_INTERVAL = 10
TERMINAL_STATUSES = {"completed", "failed", "cancelled", "error"}
DEFAULT_IDENTIFIER_COLUMNS = (
    "asset_id",
    "asset",
    "endpoint_id",
    "endpoint",
    "hostname",
    "host",
    "device",
    "device_name",
    "name",
    "id",
)

api_get = None
api_post = None
paginate_get = None


def unique_identifiers(values):
    identifiers = []
    seen = set()
    for value in values:
        normalized = normalize_identifier(value)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        identifiers.append(normalized)
    return identifiers


def parse_args(argv):
    parser = argparse.ArgumentParser(
        description=(
            "Validate assets from a CSV file and launch evidence acquisition "
            "for the assets that exist in a chosen Binalyze investigation/case."
        )
    )
    parser.add_argument("org_id", help="Organization ID")
    parser.add_argument("csv_path", help="Path to the CSV file with asset identifiers")

    target_group = parser.add_mutually_exclusive_group(required=True)
    target_group.add_argument(
        "--case-id",
        help="Existing case ID to attach acquisitions to",
    )
    target_group.add_argument(
        "--investigation-id",
        help="Existing investigation ID; the script resolves the backing case automatically",
    )

    profile_group = parser.add_mutually_exclusive_group()
    profile_group.add_argument(
        "--profile-id",
        help="Acquisition profile ID",
    )
    profile_group.add_argument(
        "--profile-name",
        help="Acquisition profile name",
    )

    parser.add_argument(
        "--column",
        help=(
            "CSV column containing asset identifiers. If omitted, the script auto-detects "
            "common names like asset, hostname, endpoint, or id."
        ),
    )
    parser.add_argument(
        "--delimiter",
        default=",",
        help=r"CSV delimiter (default: ','). Use '\t' for tab-delimited files.",
    )
    parser.add_argument(
        "--allow-duplicates",
        action="store_true",
        help="Launch acquisitions for repeated asset IDs instead of deduplicating them",
    )
    parser.add_argument(
        "--poll",
        action="store_true",
        help="Poll each launched task until it reaches a terminal state",
    )
    parser.add_argument(
        "--poll-interval",
        type=int,
        default=DEFAULT_POLL_INTERVAL,
        help=f"Seconds between poll requests (default: {DEFAULT_POLL_INTERVAL})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate and show the launch plan without calling assign-task",
    )
    parser.add_argument(
        "--report",
        help="Optional path for the JSON execution report",
    )

    args = parser.parse_args(argv)
    args.delimiter = decode_delimiter(args.delimiter)
    return args


def decode_delimiter(value):
    delimiter = value.encode("utf-8").decode("unicode_escape")
    if len(delimiter) != 1:
        raise ValueError(f"Delimiter must be exactly one character, got {value!r}")
    return delimiter


def list_organizations(air_host, api_token):
    return paginate_get(
        air_host,
        api_token,
        "/api/public/organizations",
        verbose=False,
    )


def resolve_org_scope(air_host, api_token, requested_org_id):
    requested_org_id = normalize_identifier(requested_org_id)
    if requested_org_id is None:
        raise RuntimeError("Organization ID is required.")

    organizations = list_organizations(air_host, api_token)
    matched_orgs = [
        org for org in organizations if organization_matches_identifier(org, requested_org_id)
    ]

    resp = None
    if not matched_orgs:
        resp = api_get(air_host, api_token, f"/api/public/organizations/{requested_org_id}")
        if resp.ok:
            matched_orgs = [resp.json().get("result", resp.json())]

    if requested_org_id != "0" and not matched_orgs:
        if resp is not None:
            raise RuntimeError(
                f"Could not resolve organization {requested_org_id}: "
                f"HTTP {resp.status_code} - {resp.text[:500]}"
            )
        raise RuntimeError(f"Could not resolve organization {requested_org_id}")

    candidate_orgs = matched_orgs
    if requested_org_id == "0":
        if not candidate_orgs:
            candidate_orgs = organizations
        candidate_filter_ids = unique_filterable_organization_ids(candidate_orgs)
        if not candidate_filter_ids:
            candidate_orgs = organizations
    candidate_filter_ids = unique_filterable_organization_ids(candidate_orgs)

    if not candidate_filter_ids:
        raise RuntimeError(
            f"No filterable organization ID found for requested org_id {requested_org_id}."
        )

    resolved_org = matched_orgs[0] if len(matched_orgs) == 1 else None
    resolved_org_id = organization_filter_id(resolved_org) if resolved_org else None
    if resolved_org_id == "0":
        resolved_org_id = None
    if not resolved_org_id and len(candidate_filter_ids) == 1:
        resolved_org_id = candidate_filter_ids[0]

    return {
        "requestedId": requested_org_id,
        "org": resolved_org,
        "matchedOrgs": matched_orgs,
        "candidateOrgIds": candidate_filter_ids,
        "resolvedOrgId": resolved_org_id,
    }


def get_case_filter_org_id(case):
    case_org_id = normalize_identifier(case.get("organizationId"))
    if case_org_id and case_org_id != "0":
        return case_org_id
    return None


def get_case_by_investigation_id(air_host, api_token, investigation_id, org_ids):
    for current_org_id in unique_identifiers(org_ids):
        params = {"filter[organizationIds]": current_org_id}
        cases = paginate_get(
            air_host,
            api_token,
            "/api/public/cases",
            params=params,
            verbose=False,
        )
        for case in cases:
            metadata = case.get("metadata") or {}
            if str(metadata.get("investigationId")) == str(investigation_id):
                return case
    return None


def resolve_case(air_host, api_token, org_ids, case_id=None, investigation_id=None):
    org_ids = unique_identifiers(org_ids)
    if case_id:
        resp = api_get(air_host, api_token, f"/api/public/cases/{case_id}")
        if not resp.ok:
            raise RuntimeError(
                f"Could not fetch case {case_id}: HTTP {resp.status_code}"
            )
        case = resp.json().get("result", resp.json())
    else:
        case = get_case_by_investigation_id(
            air_host,
            api_token,
            investigation_id,
            org_ids,
        )
        if not case:
            raise RuntimeError(
                "Could not find a case "
                f"for investigation {investigation_id} in org scope {', '.join(org_ids)}"
            )

    case_org_id = get_case_filter_org_id(case)
    if case_org_id and org_ids and case_org_id not in set(org_ids):
        raise RuntimeError(
            f"Case {case.get('_id') or case.get('id')} belongs to org {case_org_id}, "
            f"not {', '.join(org_ids)}"
        )
    return case


def list_profiles(air_host, api_token):
    return paginate_get(
        air_host,
        api_token,
        "/api/public/acquisitions/profiles",
        verbose=False,
    )


def choose_profile_interactively(profiles):
    print()
    print("=" * 70)
    print("ACQUISITION PROFILES")
    print("=" * 70)
    print()
    for index, profile in enumerate(profiles, 1):
        profile_id = profile.get("_id") or profile.get("id") or "?"
        profile_name = profile.get("name", "Unnamed")
        print(f"  [{index:>3}]  {profile_name}  (ID: {profile_id})")
    print()

    while True:
        try:
            choice = int(input(f"Select profile [1-{len(profiles)}]: ").strip())
        except (EOFError, ValueError):
            choice = 0
        if 1 <= choice <= len(profiles):
            return profiles[choice - 1]
        print(f"  Enter a number between 1 and {len(profiles)}.")


def resolve_profile(air_host, api_token, profile_id=None, profile_name=None):
    profiles = list_profiles(air_host, api_token)
    if not profiles:
        raise RuntimeError("No acquisition profiles found.")

    if profile_id:
        for profile in profiles:
            current_id = profile.get("_id") or profile.get("id")
            if str(current_id) == str(profile_id):
                return profile
        raise RuntimeError(f"No profile found with ID {profile_id!r}")

    if profile_name:
        for profile in profiles:
            if (profile.get("name") or "").lower() == profile_name.lower():
                return profile
        raise RuntimeError(f"No profile found with name {profile_name!r}")

    return choose_profile_interactively(profiles)


def detect_identifier_column(fieldnames, requested_column=None):
    if not fieldnames:
        raise RuntimeError("CSV file has no header row.")

    normalized = {name.strip().lower(): name for name in fieldnames if name}

    if requested_column:
        direct_match = normalized.get(requested_column.strip().lower())
        if direct_match:
            return direct_match
        raise RuntimeError(
            f"CSV column {requested_column!r} not found. Available columns: {', '.join(fieldnames)}"
        )

    for candidate in DEFAULT_IDENTIFIER_COLUMNS:
        if candidate in normalized:
            return normalized[candidate]

    if len(fieldnames) == 1:
        return fieldnames[0]

    raise RuntimeError(
        "Could not auto-detect the asset identifier column. "
        f"Use --column with one of: {', '.join(fieldnames)}"
    )


def load_csv_rows(csv_path, identifier_column=None, delimiter=","):
    with open(csv_path, "r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle, delimiter=delimiter)
        column = detect_identifier_column(reader.fieldnames or [], identifier_column)
        rows = []
        for row_number, row in enumerate(reader, start=2):
            identifier = (row.get(column) or "").strip()
            rows.append(
                {
                    "rowNumber": row_number,
                    "identifier": identifier,
                    "csvRow": row,
                }
            )
    return column, rows


def asset_id(asset):
    return asset.get("_id") or asset.get("id") or asset.get("assetId")


def asset_name(asset):
    return asset.get("name") or asset.get("hostname") or "Unknown"


def asset_org_ids(asset):
    nested_org = asset.get("organization") or {}
    return unique_identifiers(
        [
            asset.get("organizationId"),
            nested_org.get("organizationId"),
            nested_org.get("id"),
            nested_org.get("_id"),
        ]
    )


def asset_filter_org_id(asset):
    candidates = asset_org_ids(asset)
    for candidate in candidates:
        if candidate != "0":
            return candidate
    return candidates[0] if candidates else None


def asset_belongs_to_orgs(asset, org_ids):
    org_ids = set(unique_identifiers(org_ids))
    if not org_ids:
        return True
    candidates = asset_org_ids(asset)
    if not candidates:
        return True
    return any(candidate in org_ids for candidate in candidates)


def compact_asset(asset):
    return {
        "id": asset_id(asset),
        "name": asset_name(asset),
        "organizationId": asset_filter_org_id(asset),
        "platform": asset.get("platform"),
        "os": asset.get("os"),
        "ipAddress": asset.get("ipAddress"),
    }


def resolve_asset_identifier(air_host, api_token, org_ids, identifier):
    org_ids = unique_identifiers(org_ids)
    direct_asset = None
    resp = api_get(air_host, api_token, f"/api/public/assets/{identifier}")
    if resp.ok:
        candidate = resp.json().get("result", resp.json())
        if candidate and asset_id(candidate) and asset_belongs_to_orgs(candidate, org_ids):
            direct_asset = candidate

    search_results = []
    for current_org_id in org_ids:
        params = {
            "filter[organizationIds]": current_org_id,
            "search": identifier,
        }
        search_results.extend(
            paginate_get(
                air_host,
                api_token,
                "/api/public/assets",
                params=params,
                verbose=False,
            )
        )

    unique_candidates = []
    seen_asset_ids = set()
    for candidate in ([direct_asset] if direct_asset else []) + search_results:
        current_id = asset_id(candidate)
        if not current_id or current_id in seen_asset_ids:
            continue
        seen_asset_ids.add(current_id)
        unique_candidates.append(candidate)

    identifier_lower = identifier.lower()
    exact_matches = []
    partial_matches = []
    for candidate in unique_candidates:
        current_id = str(asset_id(candidate) or "")
        current_name = asset_name(candidate)
        if current_id == identifier or current_name.lower() == identifier_lower:
            exact_matches.append(candidate)
        else:
            partial_matches.append(candidate)

    if len(exact_matches) == 1:
        return {
            "status": "matched",
            "asset": compact_asset(exact_matches[0]),
        }

    if len(exact_matches) > 1:
        return {
            "status": "ambiguous",
            "reason": "multiple exact matches",
            "candidates": [compact_asset(candidate) for candidate in exact_matches[:10]],
        }

    if partial_matches:
        return {
            "status": "ambiguous",
            "reason": "partial matches only",
            "candidates": [compact_asset(candidate) for candidate in partial_matches[:10]],
        }

    return {"status": "missing"}


def assign_acquisition_task(
    air_host,
    api_token,
    org_id,
    case_id,
    profile_id,
    endpoint_id,
    dry_run=False,
):
    body = {
        "caseId": case_id,
        "endpointIds": [endpoint_id],
        "profileId": profile_id,
        "organizationId": org_id,
    }
    if dry_run:
        return {
            "ok": True,
            "statusCode": None,
            "dryRun": True,
            "requestBody": body,
            "responseBody": None,
        }

    resp = api_post(
        air_host,
        api_token,
        "/api/public/acquisitions/assign-task",
        body=body,
    )
    try:
        response_body = resp.json()
    except Exception:
        response_body = {"raw": resp.text[:2000]}

    return {
        "ok": resp.ok,
        "statusCode": resp.status_code,
        "dryRun": False,
        "requestBody": body,
        "responseBody": response_body,
    }


def extract_task_id(response_body):
    result = response_body.get("result", response_body)
    if isinstance(result, dict):
        return result.get("taskId") or result.get("_id") or result.get("id")
    if isinstance(result, list) and result:
        first = result[0]
        if isinstance(first, dict):
            return first.get("taskId") or first.get("_id") or first.get("id")
    return None


def poll_task(air_host, api_token, task_id, interval=DEFAULT_POLL_INTERVAL):
    start = time.time()
    while True:
        resp = api_get(air_host, api_token, f"/api/public/tasks/{task_id}")
        if not resp.ok:
            return {
                "ok": False,
                "statusCode": resp.status_code,
                "status": "poll_error",
                "elapsedSeconds": round(time.time() - start, 1),
            }

        task = resp.json().get("result", resp.json())
        status = (task.get("status") or "unknown").lower()
        progress = task.get("progress", 0)
        elapsed = round(time.time() - start, 1)
        print(
            f"    [{elapsed:>6.1f}s] task={task_id} status={status} progress={progress}%",
            flush=True,
        )

        if status in TERMINAL_STATUSES:
            task["elapsedSeconds"] = elapsed
            return task

        time.sleep(interval)


def default_report_path():
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return os.path.join(OUTPUT_DIR, f"bulk_acquire_report_{timestamp}.json")


def write_report(report, report_path=None):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    destination = report_path or default_report_path()
    with open(destination, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2, sort_keys=True)
    return destination


def print_case_summary(case):
    case_id = case.get("_id") or case.get("id")
    metadata = case.get("metadata") or {}
    investigation_id = metadata.get("investigationId")
    print("Target case:")
    print(f"  ID:             {case_id}")
    print(f"  Name:           {case.get('name', 'Unknown')}")
    print(f"  Status:         {case.get('status', 'Unknown')}")
    print(f"  Investigation:  {display_id(investigation_id)}")


def print_profile_summary(profile):
    profile_id = profile.get("_id") or profile.get("id")
    print("Acquisition profile:")
    print(f"  ID:    {profile_id}")
    print(f"  Name:  {profile.get('name', 'Unknown')}")


def build_report_skeleton(
    args,
    org_scope,
    case,
    profile,
    identifier_column,
    csv_path,
):
    case_id = case.get("_id") or case.get("id")
    metadata = case.get("metadata") or {}
    profile_id = profile.get("_id") or profile.get("id")
    resolved_org = org_scope.get("org")
    candidate_org_ids = org_scope.get("candidateOrgIds") or []
    resolved_org_id = org_scope.get("resolvedOrgId")
    return {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "csvPath": os.path.abspath(csv_path),
        "identifierColumn": identifier_column,
        "org": {
            "id": resolved_org_id
            or (candidate_org_ids[0] if len(candidate_org_ids) == 1 else display_id(args.org_id)),
            "requestedId": args.org_id,
            "candidateFilterIds": candidate_org_ids,
            "name": (
                resolved_org.get("name", "Unknown")
                if resolved_org
                else ("Multiple organizations" if len(candidate_org_ids) > 1 else "Unknown")
            ),
        },
        "case": {
            "id": case_id,
            "name": case.get("name"),
            "status": case.get("status"),
            "investigationId": metadata.get("investigationId"),
        },
        "profile": {
            "id": profile_id,
            "name": profile.get("name"),
        },
        "dryRun": args.dry_run,
        "allowDuplicates": args.allow_duplicates,
        "csvRows": [],
        "launches": [],
        "summary": {},
    }


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

        org_scope = resolve_org_scope(air_host, api_token, args.org_id)
        org = org_scope["org"]
        candidate_org_ids = org_scope["candidateOrgIds"]
        resolved_org_id = org_scope["resolvedOrgId"]
        if org:
            print(
                f"Organization: {org.get('name', 'Unknown')} "
                f"({organization_display_id(org)})"
            )
        else:
            print("Organization scope: Multiple organizations")

        if resolved_org_id and str(resolved_org_id) != str(args.org_id):
            print(f"  Requested org_id {args.org_id} -> using org_id {resolved_org_id}")
        elif is_zero_identifier(args.org_id) and len(candidate_org_ids) > 1:
            print(
                f"  Requested org_id {args.org_id} -> searching org_ids "
                f"{', '.join(candidate_org_ids)}"
            )

        case = resolve_case(
            air_host,
            api_token,
            candidate_org_ids,
            case_id=args.case_id,
            investigation_id=args.investigation_id,
        )
        effective_org_id = get_case_filter_org_id(case) or resolved_org_id
        if not effective_org_id:
            if len(candidate_org_ids) == 1:
                effective_org_id = candidate_org_ids[0]
            else:
                raise RuntimeError(
                    "Could not determine a filterable organization ID for the target case."
                )
        if str(effective_org_id) != str(args.org_id):
            print(f"  Effective case org_id: {effective_org_id}")
        print_case_summary(case)
        if case.get("status") not in ("open", None):
            print("Warning: target case is not open.", file=sys.stderr)

        profile = resolve_profile(
            air_host,
            api_token,
            profile_id=args.profile_id,
            profile_name=args.profile_name,
        )
        print_profile_summary(profile)

        identifier_column, csv_rows = load_csv_rows(
            args.csv_path,
            identifier_column=args.column,
            delimiter=args.delimiter,
        )
        print()
        print(f"CSV file:          {os.path.abspath(args.csv_path)}")
        print(f"Identifier column: {identifier_column}")
        print(f"Rows loaded:       {len(csv_rows)}")

        report = build_report_skeleton(
            args,
            org_scope,
            case,
            profile,
            identifier_column,
            args.csv_path,
        )

        resolution_cache = {}
        scheduled_asset_ids = set()
        scheduled = []
        asset_search_org_ids = unique_identifiers([effective_org_id] + candidate_org_ids)

        print()
        print("Validating CSV assets against Binalyze...")
        for entry in csv_rows:
            identifier = entry["identifier"]
            row_report = {
                "rowNumber": entry["rowNumber"],
                "identifier": identifier,
                "status": None,
            }

            if not identifier:
                row_report["status"] = "blank"
                report["csvRows"].append(row_report)
                continue

            if identifier not in resolution_cache:
                resolution_cache[identifier] = resolve_asset_identifier(
                    air_host,
                    api_token,
                    asset_search_org_ids,
                    identifier,
                )

            resolution = resolution_cache[identifier]
            row_report.update(resolution)

            if resolution["status"] == "matched":
                matched_asset = resolution["asset"]
                current_asset_id = matched_asset["id"]
                if not args.allow_duplicates and current_asset_id in scheduled_asset_ids:
                    row_report["status"] = "duplicate_skipped"
                else:
                    scheduled_asset_ids.add(current_asset_id)
                    scheduled.append(
                        {
                            "rowNumber": entry["rowNumber"],
                            "identifier": identifier,
                            "asset": matched_asset,
                        }
                    )
            report["csvRows"].append(row_report)

        matched_rows = [row for row in report["csvRows"] if row["status"] == "matched"]
        missing_rows = [row for row in report["csvRows"] if row["status"] == "missing"]
        ambiguous_rows = [row for row in report["csvRows"] if row["status"] == "ambiguous"]
        blank_rows = [row for row in report["csvRows"] if row["status"] == "blank"]
        duplicate_rows = [
            row for row in report["csvRows"] if row["status"] == "duplicate_skipped"
        ]

        print(f"  Matched rows:      {len(matched_rows)}")
        print(f"  Missing rows:      {len(missing_rows)}")
        print(f"  Ambiguous rows:    {len(ambiguous_rows)}")
        print(f"  Blank rows:        {len(blank_rows)}")
        print(f"  Duplicate skips:   {len(duplicate_rows)}")
        print(f"  Assets to launch:  {len(scheduled)}")

        if not scheduled:
            report["summary"] = {
                "rowsLoaded": len(csv_rows),
                "matchedRows": len(matched_rows),
                "missingRows": len(missing_rows),
                "ambiguousRows": len(ambiguous_rows),
                "blankRows": len(blank_rows),
                "duplicateSkippedRows": len(duplicate_rows),
                "scheduledAssets": 0,
                "successfulLaunches": 0,
                "failedLaunches": 0,
            }
            report_path = write_report(report, args.report)
            print()
            print(f"No assets were eligible for launch. Report written to {report_path}")
            sys.exit(1)

        print()
        print("Launching acquisitions...")
        profile_id = profile.get("_id") or profile.get("id")
        case_id = case.get("_id") or case.get("id")

        successful_launches = 0
        failed_launches = 0

        for index, item in enumerate(scheduled, 1):
            current_asset = item["asset"]
            current_asset_id = current_asset["id"]
            current_asset_name = current_asset["name"]
            print(
                f"  [{index}/{len(scheduled)}] {current_asset_name} "
                f"({current_asset_id}) from row {item['rowNumber']}"
            )

            launch_record = {
                "rowNumber": item["rowNumber"],
                "identifier": item["identifier"],
                "asset": current_asset,
            }

            try:
                launch_result = assign_acquisition_task(
                    air_host,
                    api_token,
                    effective_org_id,
                    case_id,
                    profile_id,
                    current_asset_id,
                    dry_run=args.dry_run,
                )
                launch_record.update(launch_result)

                if launch_result["ok"]:
                    successful_launches += 1
                    if args.dry_run:
                        print("    Dry run only, no API call sent.")
                    else:
                        task_id = extract_task_id(launch_result["responseBody"] or {})
                        if task_id:
                            launch_record["taskId"] = task_id
                            print(f"    Task ID: {task_id}")
                            if args.poll:
                                launch_record["pollResult"] = poll_task(
                                    air_host,
                                    api_token,
                                    task_id,
                                    interval=args.poll_interval,
                                )
                        else:
                            print("    Warning: task ID not found in response.", file=sys.stderr)
                else:
                    failed_launches += 1
                    print(
                        f"    Launch failed with HTTP {launch_result['statusCode']}",
                        file=sys.stderr,
                    )
            except Exception as exc:
                failed_launches += 1
                launch_record.update(
                    {
                        "ok": False,
                        "error": str(exc),
                    }
                )
                print(f"    Launch failed: {exc}", file=sys.stderr)

            report["launches"].append(launch_record)

        report["summary"] = {
            "rowsLoaded": len(csv_rows),
            "matchedRows": len(matched_rows),
            "missingRows": len(missing_rows),
            "ambiguousRows": len(ambiguous_rows),
            "blankRows": len(blank_rows),
            "duplicateSkippedRows": len(duplicate_rows),
            "scheduledAssets": len(scheduled),
            "successfulLaunches": successful_launches,
            "failedLaunches": failed_launches,
        }
        report_path = write_report(report, args.report)

        print()
        print("Execution summary:")
        print(f"  Successful launches: {successful_launches}")
        print(f"  Failed launches:     {failed_launches}")
        print(f"  Report:              {report_path}")

        if failed_launches:
            sys.exit(2)

    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
