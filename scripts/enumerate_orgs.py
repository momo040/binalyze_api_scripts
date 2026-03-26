import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib.runtime import load_api_context


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
            oid = org.get("_id") or org.get("id") or org.get("organizationId")
            name = org.get("name")
            print(f"- ID: {oid}  Name: {name}")
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
