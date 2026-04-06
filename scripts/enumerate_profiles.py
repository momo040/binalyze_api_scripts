import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib.runtime import load_api_context


paginate_get = None


def parse_args(argv):
    parser = argparse.ArgumentParser(
        description="List available acquisition profiles in the current Binalyze tenant."
    )
    parser.add_argument("org_id", help="Organization ID")
    return parser.parse_args(argv)


def profile_id(profile):
    return profile.get("_id") or profile.get("id")


def profile_name(profile):
    return profile.get("name") or "Unnamed"


def main():
    global paginate_get

    args = parse_args(sys.argv[1:])

    try:
        air_host, api_token, _, _, runtime_paginate_get = load_api_context()
        paginate_get = runtime_paginate_get

        print(f"Connecting to {air_host}/api/public/acquisitions/profiles...")
        profiles = paginate_get(
            air_host,
            api_token,
            "/api/public/acquisitions/profiles",
            params={
                "organizationId": str(args.org_id),
                "filter[organizationIds]": str(args.org_id),
            },
            verbose=False,
        )

        print(f"\nFound {len(profiles)} profile(s):")
        if not profiles:
            print("  (No profiles found)")
            return

        for profile in profiles:
            print(f"- ID: {profile_id(profile) or '?'}  Name: {profile_name(profile)}")
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()