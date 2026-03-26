import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib.runtime import (
    organization_candidate_ids,
    organization_display_id,
    load_api_context,
)


paginate_get = None


def parse_args(argv):
    parser = argparse.ArgumentParser(
        description="List all organizations in the current Binalyze tenant."
    )
    return parser.parse_args(argv)


def main():
    global paginate_get

    parse_args(sys.argv[1:])

    try:
        air_host, api_token, _, _, runtime_paginate_get = load_api_context()
        paginate_get = runtime_paginate_get

        print(f"Connecting to {air_host}/api/public/organizations...")
        orgs = paginate_get(air_host, api_token, "/api/public/organizations")

        print(f"\nFound {len(orgs)} organization(s):")
        for org in orgs:
            oid = organization_display_id(org)
            name = org.get("name")
            raw_ids = organization_candidate_ids(org)
            raw_note = ""
            if raw_ids and str(oid) not in raw_ids:
                raw_note = f"  Raw IDs: {', '.join(raw_ids)}"
            elif raw_ids and raw_ids[0] != str(oid):
                raw_note = f"  Raw IDs: {', '.join(raw_ids)}"
            print(f"- ID: {oid}  Name: {name}{raw_note}")
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
