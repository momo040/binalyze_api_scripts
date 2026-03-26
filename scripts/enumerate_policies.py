import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib.runtime import load_api_context


paginate_get = None


def parse_args(argv):
    parser = argparse.ArgumentParser(
        description="List available policies in the current Binalyze tenant."
    )
    return parser.parse_args(argv)


def policy_id(policy):
    return policy.get("_id") or policy.get("id") or policy.get("policyId")


def policy_name(policy):
    return policy.get("name") or policy.get("policyName") or "Unnamed"


def main():
    global paginate_get

    parse_args(sys.argv[1:])

    try:
        air_host, api_token, _, _, runtime_paginate_get = load_api_context()
        paginate_get = runtime_paginate_get

        print(f"Connecting to {air_host}/api/public/policies...")
        policies = paginate_get(air_host, api_token, "/api/public/policies", verbose=False)

        print(f"\nFound {len(policies)} policy(s):")
        if not policies:
            print("  (No policies found)")
            return

        for policy in policies:
            print(f"- ID: {policy_id(policy) or '?'}  Name: {policy_name(policy)}")
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
