import importlib
import unittest


class FakeResponse:
    def __init__(self, ok, payload=None):
        self.ok = ok
        self._payload = payload or {}

    def json(self):
        return self._payload


class AssetNameLookupTests(unittest.TestCase):
    def test_bulk_acquire_uses_name_search_before_direct_asset_lookup(self):
        module = importlib.import_module("scripts.investigation_acquire_from_csv")
        original_api_get = module.api_get
        original_paginate_get = module.paginate_get
        calls = []

        def fake_paginate_get(air_host, api_token, path, params=None, verbose=False):
            calls.append(("paginate_get", path, params))
            return [
                {
                    "_id": "asset-123",
                    "name": "HOST-01",
                    "organizationId": 0,
                }
            ]

        def fake_api_get(air_host, api_token, path, params=None):
            calls.append(("api_get", path, params))
            raise AssertionError("direct asset lookup should not run when name search matches")

        module.paginate_get = fake_paginate_get
        module.api_get = fake_api_get
        try:
            result = module.resolve_asset_identifier("host", "token", 0, "HOST-01")
        finally:
            module.api_get = original_api_get
            module.paginate_get = original_paginate_get

        self.assertEqual(result["status"], "matched")
        self.assertEqual(result["asset"]["id"], "asset-123")
        self.assertEqual(
            calls,
            [
                (
                    "paginate_get",
                    "/api/public/assets",
                    {"filter[organizationIds]": "0", "filter[name]": "HOST-01"},
                )
            ],
        )

    def test_case_acquire_uses_name_search_before_direct_asset_lookup(self):
        module = importlib.import_module("scripts.case_acquire")
        original_api_get = module.api_get
        original_paginate_get = module.paginate_get
        calls = []

        def fake_paginate_get(air_host, api_token, path, params=None, verbose=False):
            calls.append(("paginate_get", path, params))
            return [
                {
                    "_id": "asset-456",
                    "name": "HOST-02",
                    "organizationId": 0,
                    "platform": "windows",
                    "ipAddress": "10.0.0.5",
                }
            ]

        def fake_api_get(air_host, api_token, path, params=None):
            calls.append(("api_get", path, params))
            raise AssertionError("direct asset lookup should not run when name search matches")

        module.paginate_get = fake_paginate_get
        module.api_get = fake_api_get
        try:
            asset = module.find_endpoint("host", "token", "HOST-02", 0)
        finally:
            module.api_get = original_api_get
            module.paginate_get = original_paginate_get

        self.assertEqual(asset["_id"], "asset-456")
        self.assertEqual(
            calls,
            [
                (
                    "paginate_get",
                    "/api/public/assets",
                    {"filter[organizationIds]": "0", "filter[name]": "HOST-02"},
                )
            ],
        )


if __name__ == "__main__":
    unittest.main()
