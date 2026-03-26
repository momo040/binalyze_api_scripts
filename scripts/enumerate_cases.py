import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib.runtime import load_api_context


paginate_get = None


def parse_args(argv):
    parser = argparse.ArgumentParser(
        description="List cases for an organization, optionally filtered by status."
    )
    parser.add_argument("org_id", help="Organization ID")
    parser.add_argument(
        "status",
        nargs="?",
        default="open",
        help="Case status filter (default: open)",
    )
    return parser.parse_args(argv)


def main():
    global paginate_get

    args = parse_args(sys.argv[1:])

    try:
        air_host, api_token, _, _, runtime_paginate_get = load_api_context()
        paginate_get = runtime_paginate_get

        print(f"Connecting to {air_host}/api/public/cases...")
        print(
            f"Fetching cases for organization ID: {args.org_id}, status: {args.status}"
        )

        params = {
            "filter[organizationIds]": args.org_id,
            "filter[status]": args.status,
        }

        cases = paginate_get(air_host, api_token, "/api/public/cases", params=params)

        print(f"\nFound {len(cases)} {args.status} case(s) in organization {args.org_id}:")

        if not cases:
            print("  (No cases found)")
        else:
            for case in cases:
                case_id = case.get("_id") or case.get("id") or case.get("caseId")
                name = case.get("name") or case.get("title")
                status = case.get("status")
                created = case.get("createdAt")
                owner = case.get("owner")
                metadata = case.get("metadata") or {}
                investigation_id = metadata.get("investigationId")

                print(f"\n- Case ID: {case_id}")
                print(f"  Name: {name}")
                print(f"  Status: {status}")
                print(f"  Owner: {owner}")
                print(f"  Created: {created}")
                print(f"  Investigation ID: {investigation_id}")
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
