import os
from functools import lru_cache


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "output")


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
