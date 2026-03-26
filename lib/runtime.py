import os
from copy import deepcopy
from functools import lru_cache


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "output")

DEFAULT_DRONE_CONFIG = {
    "autoPilot": False,
    "enabled": False,
    "analyzers": ["bha", "wsa", "aa", "ara"],
    "keywords": [],
}

DEFAULT_TASK_CONFIG = {
    "choice": "use-custom-options",
    "saveTo": {
        "windows": {
            "location": "local",
            "useMostFreeVolume": True,
            "repositoryId": None,
            "path": "Binalyze\\AIR\\",
            "volume": "C:",
            "tmp": "Binalyze\\AIR\\tmp",
            "directCollection": False,
        },
        "linux": {
            "location": "local",
            "useMostFreeVolume": True,
            "repositoryId": None,
            "path": "opt/binalyze/air",
            "tmp": "opt/binalyze/air/tmp",
            "directCollection": False,
        },
        "macos": {
            "location": "local",
            "useMostFreeVolume": False,
            "repositoryId": None,
            "path": "opt/binalyze/air",
            "volume": "/",
            "tmp": "opt/binalyze/air/tmp",
            "directCollection": False,
        },
        "aix": {
            "location": "local",
            "useMostFreeVolume": True,
            "path": "opt/binalyze/air",
            "volume": "/",
            "tmp": "opt/binalyze/air/tmp",
            "directCollection": False,
        },
    },
    "cpu": {
        "limit": 80,
    },
    "compression": {
        "enabled": True,
        "encryption": {
            "enabled": False,
            "password": "",
        },
    },
}

DEFAULT_ACQUISITION_FILTER = {
    "searchTerm": "",
    "name": "",
    "ipAddress": "",
    "groupId": "",
    "groupFullPath": "",
    "isolationStatus": [],
    "platform": [],
    "issue": "",
    "onlineStatus": [],
    "tags": [],
    "version": "",
    "policy": "",
    "includedEndpointIds": [],
    "excludedEndpointIds": [],
    "organizationIds": [],
}


def display_id(value, missing=0):
    if value is None or value == "":
        return missing
    return value


def coerce_identifier_value(value):
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.isdigit():
            return int(stripped)
        return stripped
    return value


def build_acquisition_request(case_id, acquisition_profile_id, endpoint_id, org_id):
    body = {
        "caseId": case_id,
        "droneConfig": deepcopy(DEFAULT_DRONE_CONFIG),
        "taskConfig": deepcopy(DEFAULT_TASK_CONFIG),
        "acquisitionProfileId": acquisition_profile_id,
        "filter": deepcopy(DEFAULT_ACQUISITION_FILTER),
    }
    body["filter"]["includedEndpointIds"] = [endpoint_id]
    body["filter"]["organizationIds"] = [coerce_identifier_value(org_id)]
    return body


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
