import importlib
import unittest


class FakeResponse:
    def __init__(self, ok, payload=None):
        self.ok = ok
        self._payload = payload or {}

    def json(self):
        return self._payload


class ZeroOrgPassthroughTests(unittest.TestCase):
    def setUp(self):
        self.module = importlib.import_module("scripts.investigation_acquire_from_csv")
        self.original_api_get = self.module.api_get
        self.original_paginate_get = self.module.paginate_get

    def tearDown(self):
        self.module.api_get = self.original_api_get
        self.module.paginate_get = self.original_paginate_get

    def test_case_lookup_keeps_zero_org_filter(self):
        calls = []

        def fake_paginate_get(air_host, api_token, path, params=None, verbose=False):
            calls.append((path, params))
            raise RuntimeError("HTTP 400: {success:false errors: organizationID(s) is required}")

        self.module.paginate_get = fake_paginate_get

        with self.assertRaises(RuntimeError) as excinfo:
            self.module.get_case_by_investigation_id("host", "token", "INV-1", 0)

        self.assertIn("filter[organizationIds]=0", str(excinfo.exception))
        self.assertEqual(
            calls,
            [("/api/public/cases", {"filter[organizationIds]": "0"})],
        )

    def test_asset_lookup_keeps_zero_org_filter(self):
        calls = []

        def fake_api_get(air_host, api_token, path, params=None):
            return FakeResponse(False, {})

        def fake_paginate_get(air_host, api_token, path, params=None, verbose=False):
            calls.append((path, params))
            raise RuntimeError("HTTP 400: {success:false errors: organizationID(s) is required}")

        self.module.api_get = fake_api_get
        self.module.paginate_get = fake_paginate_get

        with self.assertRaises(RuntimeError) as excinfo:
            self.module.resolve_asset_identifier("host", "token", 0, "endpoint-1")

        self.assertIn("filter[organizationIds]=0", str(excinfo.exception))
        self.assertEqual(
            calls,
            [
                (
                    "/api/public/assets",
                    {"filter[organizationIds]": "0", "search": "endpoint-1"},
                )
            ],
        )


if __name__ == "__main__":
    unittest.main()
