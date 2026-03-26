"""
Acquire evidence from an endpoint via the Binalyze AIR API.

Replicates the console acquisition workflow programmatically:
  1. Validate organization
  2. Find endpoint (asset) by name or ID
  3. Select an acquisition profile
  4. Create or reuse a case
  5. Assign the acquisition task (POST /acquisitions/assign-task)
  6. Optionally poll until task completes

NOTE: The POST /acquisitions/assign-task request body schema is inferred from
SDK patterns and may need adjustment. The script prints the full request and
response bodies to aid debugging. Use --dry-run to preview without sending.
"""

import json
import os
import sys
import time
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib.runtime import (
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

    candidate_orgs = matched_orgs or organizations
    candidate_org_ids = unique_filterable_organization_ids(candidate_orgs)
    if requested_org_id == "0" and not candidate_org_ids:
        candidate_org_ids = unique_filterable_organization_ids(organizations)

    if not candidate_org_ids:
        raise RuntimeError(
            f"No filterable organization ID found for requested org_id {requested_org_id}."
        )

    resolved_org = matched_orgs[0] if len(matched_orgs) == 1 else None
    resolved_org_id = organization_filter_id(resolved_org) if resolved_org else None
    if resolved_org_id == "0":
        resolved_org_id = None
    if not resolved_org_id and len(candidate_org_ids) == 1:
        resolved_org_id = candidate_org_ids[0]

    return {
        "requestedId": requested_org_id,
        "org": resolved_org,
        "candidateOrgIds": candidate_org_ids,
        "resolvedOrgId": resolved_org_id,
    }


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


def get_case_filter_org_id(case):
    case_org_id = normalize_identifier(case.get("organizationId"))
    if case_org_id and case_org_id != "0":
        return case_org_id
    return None


# ---------------------------------------------------------------------------
# API helpers
# ---------------------------------------------------------------------------
def find_endpoint(air_host, api_token, identifier, org_ids):
    """Find an endpoint by name or ID. Tries search first, falls back to direct get."""
    org_ids = unique_identifiers(org_ids)
    # Try direct ID lookup first
    resp = api_get(air_host, api_token, f"/api/public/assets/{identifier}")
    if resp.ok:
        asset = resp.json().get("result", resp.json())
        if (asset.get("_id") or asset.get("id") or asset.get("assetId")) and asset_belongs_to_orgs(asset, org_ids):
            return asset

    assets = []
    for current_org_id in org_ids:
        params = {
            "filter[organizationIds]": current_org_id,
            "search": identifier,
        }
        assets.extend(
            paginate_get(
                air_host, api_token, "/api/public/assets", params=params, verbose=False,
            )
        )
    unique_assets = []
    seen_asset_ids = set()
    for asset in assets:
        asset_id = asset.get("_id") or asset.get("id") or asset.get("assetId")
        if not asset_id or asset_id in seen_asset_ids:
            continue
        seen_asset_ids.add(asset_id)
        unique_assets.append(asset)
    assets = unique_assets

    if not assets:
        print(f"Error: No endpoint found matching '{identifier}'", file=sys.stderr)
        sys.exit(1)

    # Exact name match preferred
    for asset in assets:
        if asset.get("name", "").lower() == identifier.lower():
            return asset

    if len(assets) == 1:
        return assets[0]

    # Multiple matches -- interactive selection
    print(f"\n  Multiple endpoints match '{identifier}':\n")
    for i, a in enumerate(assets, 1):
        name = a.get("name", "Unknown")
        platform = a.get("platform", "?")
        ip = a.get("ipAddress", "?")
        print(f"  [{i:>3}]  {name}  ({platform}, {ip})")

    print()
    while True:
        try:
            choice = input(f"Select endpoint [1-{len(assets)}]: ").strip()
            idx = int(choice) - 1
            if 0 <= idx < len(assets):
                return assets[idx]
            print(f"  Enter a number between 1 and {len(assets)}.")
        except (ValueError, EOFError):
            print(f"  Enter a number between 1 and {len(assets)}.")


def list_profiles(air_host, api_token):
    return paginate_get(
        air_host, api_token, "/api/public/acquisitions/profiles", verbose=False,
    )


def resolve_profile(air_host, api_token, profile_id=None, profile_name=None):
    """Find a profile by ID, by name, or let the user pick interactively."""
    profiles = list_profiles(air_host, api_token)
    if not profiles:
        print("Error: No acquisition profiles found.", file=sys.stderr)
        sys.exit(1)

    if profile_id:
        for p in profiles:
            if str(p.get("_id")) == str(profile_id) or str(p.get("id")) == str(profile_id):
                return p
        print(f"Error: No profile found with ID '{profile_id}'", file=sys.stderr)
        sys.exit(1)

    if profile_name:
        for p in profiles:
            if (p.get("name") or "").lower() == profile_name.lower():
                return p
        print(f"Error: No profile found with name '{profile_name}'", file=sys.stderr)
        sys.exit(1)

    # Interactive selection
    print(f"\n{'='*70}")
    print("ACQUISITION PROFILES")
    print(f"{'='*70}\n")

    for i, p in enumerate(profiles, 1):
        name = p.get("name", "Unnamed")
        pid = p.get("_id") or p.get("id") or "?"
        print(f"  [{i:>3}]  {name}  (ID: {pid})")

    print()
    while True:
        try:
            choice = input(f"Select profile [1-{len(profiles)}]: ").strip()
            idx = int(choice) - 1
            if 0 <= idx < len(profiles):
                return profiles[idx]
            print(f"  Enter a number between 1 and {len(profiles)}.")
        except (ValueError, EOFError):
            print(f"  Enter a number between 1 and {len(profiles)}.")


def resolve_case(air_host, api_token, org_id, case_id=None, case_name=None,
                 endpoint_name="unknown"):
    """Fetch an existing case or create a new one."""
    if case_id:
        resp = api_get(air_host, api_token, f"/api/public/cases/{case_id}")
        if not resp.ok:
            print(f"Error: Could not fetch case {case_id}: HTTP {resp.status_code}",
                  file=sys.stderr)
            sys.exit(1)
        case = resp.json().get("result", resp.json())
        status = case.get("status", "unknown")
        if status not in ("open",):
            print(f"Warning: Case '{case.get('name')}' has status '{status}' (not open).",
                  file=sys.stderr)
        case_org_id = get_case_filter_org_id(case)
        if case_org_id and str(case_org_id) != str(org_id):
            print(
                f"Error: Case '{case.get('name')}' belongs to org {case_org_id}, not {org_id}.",
                file=sys.stderr,
            )
            sys.exit(1)
        return case

    if not case_name:
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        case_name = f"Acquisition - {endpoint_name} - {date_str}"

    body = {
        "name": case_name,
        "organizationId": org_id,
    }
    print(f"  Creating case: {case_name}")
    resp = api_post(air_host, api_token, "/api/public/cases", body=body)
    if not resp.ok:
        print(f"Error: Failed to create case: HTTP {resp.status_code}", file=sys.stderr)
        print(f"  Response: {resp.text[:500]}", file=sys.stderr)
        sys.exit(1)

    case = resp.json().get("result", resp.json())
    print(f"  Case created: {case.get('_id') or case.get('id')}")
    return case


def assign_acquisition(air_host, api_token, case_id, endpoint_id, profile_id,
                       org_id, dry_run=False):
    """Call POST /acquisitions/assign-task. Prints request/response for debugging."""
    body = {
        "caseId": case_id,
        "endpointIds": [endpoint_id],
        "profileId": profile_id,
        "organizationId": org_id,
    }

    print(f"\n{'─'*70}")
    print("ASSIGN ACQUISITION TASK")
    print(f"{'─'*70}\n")
    print(f"  POST /api/public/acquisitions/assign-task")
    print(f"  Request body:")
    print(f"  {json.dumps(body, indent=4)}")

    if dry_run:
        print(f"\n  [DRY RUN] Stopping before API call.")
        return None

    resp = api_post(air_host, api_token, "/api/public/acquisitions/assign-task", body=body)

    print(f"\n  Response: HTTP {resp.status_code}")
    try:
        resp_body = resp.json()
        print(f"  {json.dumps(resp_body, indent=4)[:2000]}")
    except Exception:
        print(f"  {resp.text[:2000]}")

    if not resp.ok:
        print(f"\nError: assign-task failed with HTTP {resp.status_code}.", file=sys.stderr)
        print("The request body schema is a best guess and may need adjustment.",
              file=sys.stderr)
        print("Check the response above for clues on the expected format.",
              file=sys.stderr)
        sys.exit(1)

    return resp_body


def poll_task(air_host, api_token, task_id, interval=DEFAULT_POLL_INTERVAL):
    """Poll GET /tasks/{id} until the task reaches a terminal state."""
    print(f"\n{'─'*70}")
    print(f"POLLING TASK: {task_id}")
    print(f"{'─'*70}\n")

    start = time.time()
    while True:
        resp = api_get(air_host, api_token, f"/api/public/tasks/{task_id}")
        if not resp.ok:
            print(f"  Poll error: HTTP {resp.status_code}", file=sys.stderr)
            break

        task = resp.json().get("result", resp.json())
        status = task.get("status", "unknown")
        progress = task.get("progress", 0)
        elapsed = time.time() - start

        print(f"  [{elapsed:>6.0f}s]  status={status}  progress={progress}%", flush=True)

        if status.lower() in TERMINAL_STATUSES:
            print(f"\n  Task finished: {status} (elapsed: {elapsed:.0f}s)")
            duration = task.get("duration")
            if duration:
                print(f"  Server-reported duration: {duration / 1000:.1f}s")
            return task

        time.sleep(interval)

    return None


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def print_usage():
    print("Usage: python3 scripts/case_acquire.py <org_id> <endpoint_name_or_id> [options]")
    print()
    print("Arguments:")
    print("  org_id                Organization ID")
    print("  endpoint_name_or_id   Endpoint hostname or asset ID")
    print()
    print("Options:")
    print("  --case-id ID          Use an existing case (skip creation)")
    print("  --case-name NAME      Create a new case with this name")
    print("  --profile-id ID       Acquisition profile ID (skip interactive selection)")
    print("  --profile-name NAME   Find acquisition profile by name")
    print("  --poll                Poll for task completion after assignment")
    print("  --poll-interval SECS  Seconds between status checks (default: 10)")
    print("  --dry-run             Show what would be sent without calling assign-task")
    print()
    print("Examples:")
    print("  python3 scripts/case_acquire.py 362 WORKSTATION-01")
    print("  python3 scripts/case_acquire.py 362 WORKSTATION-01 --profile-name 'Full' --poll")
    print("  python3 scripts/case_acquire.py 362 WORKSTATION-01 --case-id C-2026-00001 --dry-run")


def parse_args(argv):
    args = {
        "org_id": None,
        "endpoint": None,
        "case_id": None,
        "case_name": None,
        "profile_id": None,
        "profile_name": None,
        "poll": False,
        "poll_interval": DEFAULT_POLL_INTERVAL,
        "dry_run": False,
    }

    positional = []
    i = 0
    while i < len(argv):
        if argv[i] == "--case-id" and i + 1 < len(argv):
            args["case_id"] = argv[i + 1]
            i += 2
        elif argv[i] == "--case-name" and i + 1 < len(argv):
            args["case_name"] = argv[i + 1]
            i += 2
        elif argv[i] == "--profile-id" and i + 1 < len(argv):
            args["profile_id"] = argv[i + 1]
            i += 2
        elif argv[i] == "--profile-name" and i + 1 < len(argv):
            args["profile_name"] = argv[i + 1]
            i += 2
        elif argv[i] == "--poll-interval" and i + 1 < len(argv):
            args["poll_interval"] = int(argv[i + 1])
            i += 2
        elif argv[i] == "--poll":
            args["poll"] = True
            i += 1
        elif argv[i] == "--dry-run":
            args["dry_run"] = True
            i += 1
        elif argv[i] in ("--help", "-h"):
            print_usage()
            sys.exit(0)
        else:
            positional.append(argv[i])
            i += 1

    if len(positional) >= 1:
        args["org_id"] = positional[0]
    if len(positional) >= 2:
        args["endpoint"] = positional[1]

    return args


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main():
    global api_get, api_post, paginate_get

    args = parse_args(sys.argv[1:])

    if not args["org_id"] or not args["endpoint"]:
        print_usage()
        sys.exit(1)

    requested_org_id = args["org_id"]
    endpoint_identifier = args["endpoint"]

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

        # Step 1: Resolve organization scope
        print("Validating organization...", flush=True)
        org_scope = resolve_org_scope(air_host, api_token, requested_org_id)
        org = org_scope["org"]
        candidate_org_ids = org_scope["candidateOrgIds"]
        resolved_org_id = org_scope["resolvedOrgId"]
        if org:
            print(
                f"  Organization: {org.get('name', 'Unknown')} "
                f"({organization_display_id(org)})"
            )
        else:
            print("  Organization scope: Multiple organizations")
        if resolved_org_id and str(resolved_org_id) != str(requested_org_id):
            print(f"  Requested org_id {requested_org_id} -> using org_id {resolved_org_id}")
        elif is_zero_identifier(requested_org_id) and len(candidate_org_ids) > 1:
            print(
                f"  Requested org_id {requested_org_id} -> searching org_ids "
                f"{', '.join(candidate_org_ids)}"
            )

        # Step 2: Find endpoint
        print(f"\nFinding endpoint '{endpoint_identifier}'...", flush=True)
        asset = find_endpoint(air_host, api_token, endpoint_identifier, candidate_org_ids)
        endpoint_id = asset.get("_id") or asset.get("id")
        endpoint_name = asset.get("name", "Unknown")
        effective_org_id = asset_filter_org_id(asset) or resolved_org_id
        if not effective_org_id:
            if len(candidate_org_ids) == 1:
                effective_org_id = candidate_org_ids[0]
            else:
                raise RuntimeError(
                    "Could not determine a filterable organization ID for the selected endpoint."
                )
        print(f"  Endpoint: {endpoint_name}")
        print(f"  ID:       {endpoint_id}")
        print(f"  OS:       {asset.get('os', 'N/A')} ({asset.get('platform', 'N/A')})")
        print(f"  IP:       {asset.get('ipAddress', 'N/A')}")
        if str(effective_org_id) != str(requested_org_id):
            print(f"  Effective endpoint org_id: {effective_org_id}")

        # Step 3: Resolve acquisition profile
        print(f"\nResolving acquisition profile...", flush=True)
        profile = resolve_profile(
            air_host, api_token,
            profile_id=args["profile_id"],
            profile_name=args["profile_name"],
        )
        profile_id = profile.get("_id") or profile.get("id")
        profile_name = profile.get("name", "Unknown")
        print(f"  Profile: {profile_name} (ID: {profile_id})")

        # Step 4: Resolve case
        print(f"\nResolving case...", flush=True)
        case = resolve_case(
            air_host, api_token, effective_org_id,
            case_id=args["case_id"],
            case_name=args["case_name"],
            endpoint_name=endpoint_name,
        )
        case_id = case.get("_id") or case.get("id")
        print(f"  Case: {case.get('name', 'Unknown')} ({case_id})")
        print(f"  Status: {case.get('status', 'N/A')}")

        # Step 5: Assign acquisition task
        result = assign_acquisition(
            air_host, api_token, case_id, endpoint_id, profile_id, effective_org_id,
            dry_run=args["dry_run"],
        )

        if args["dry_run"] or result is None:
            print("\nDone (dry run).\n")
            sys.exit(0)

        # Step 6: Poll for completion (optional)
        task_id = None
        r = result.get("result", result)
        if isinstance(r, dict):
            task_id = r.get("taskId") or r.get("_id") or r.get("id")
        elif isinstance(r, list) and r:
            task_id = r[0].get("taskId") or r[0].get("_id") or r[0].get("id")

        if task_id:
            print(f"\n  Task ID: {task_id}")

        if args["poll"] and task_id:
            poll_task(air_host, api_token, task_id, interval=args["poll_interval"])
        elif args["poll"] and not task_id:
            print("\n  Warning: --poll requested but could not extract task ID from response.",
                  file=sys.stderr)

        print("\nDone.\n")

    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
