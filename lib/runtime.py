import os
from functools import lru_cache


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "output")
ORGANIZATION_ID_FIELDS = ("organizationId", "id", "_id")


def display_id(value, missing=0):
    if value is None or value == "":
        return missing
    return value


def has_value(value):
    return value is not None and value != ""


def normalize_identifier(value):
    if not has_value(value):
        return None
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return None
    return str(value)


def is_zero_identifier(value):
    return normalize_identifier(value) == "0"


def organization_candidate_ids(org):
    candidates = []
    for field in ORGANIZATION_ID_FIELDS:
        normalized = normalize_identifier(org.get(field))
        if normalized and normalized not in candidates:
            candidates.append(normalized)
    return candidates


def organization_filter_id(org):
    fallback = None
    for field in ORGANIZATION_ID_FIELDS:
        normalized = normalize_identifier(org.get(field))
        if not normalized:
            continue
        if normalized != "0":
            return normalized
        if fallback is None:
            fallback = normalized
    return fallback


def organization_display_id(org, missing=0):
    filter_id = organization_filter_id(org)
    if filter_id and filter_id != "0":
        return filter_id
    candidates = organization_candidate_ids(org)
    if candidates:
        return candidates[0]
    return missing


def organization_matches_identifier(org, requested_org_id):
    requested = normalize_identifier(requested_org_id)
    if requested is None:
        return False
    return requested in organization_candidate_ids(org)


def unique_filterable_organization_ids(orgs):
    filter_ids = []
    seen = set()
    for org in orgs:
        current_id = organization_filter_id(org)
        if not current_id or current_id == "0" or current_id in seen:
            continue
        seen.add(current_id)
        filter_ids.append(current_id)
    return filter_ids


@lru_cache(maxsize=1)
def load_api_runtime():
    try:
        from lib.api_client import load_config, api_get, api_post
        from lib.pagination import paginate_get
    except ModuleNotFoundError as exc:
        missing_name = exc.name or "unknown"
        if missing_name.startswith("lib"):
            raise
        raise RuntimeError(
            "Missing dependency while loading the Binalyze client. "
            "Install requirements with `pip install -r requirements.txt`."
        ) from exc

    return load_config, api_get, api_post, paginate_get


def load_api_context():
    load_config, api_get, api_post, paginate_get = load_api_runtime()
    air_host, api_token = load_config()
    return air_host, api_token, api_get, api_post, paginate_get
