import importlib
import unittest


class FakeResponse:
    def __init__(self, ok, payload=None, status_code=200, text=""):
        self.ok = ok
        self._payload = payload or {}
        self.status_code = status_code
        self.text = text

    def json(self):
        return self._payload


class InvestigationAcquireOrgScopeTests(unittest.TestCase):
    def setUp(self):
        self.module = importlib.import_module("scripts.investigation_acquire_from_csv")
        self.original_api_get = self.module.api_get
        self.original_paginate_get = self.module.paginate_get

    def tearDown(self):
        self.module.api_get = self.original_api_get
        self.module.paginate_get = self.original_paginate_get

    def test_resolve_org_scope_remaps_zero_to_filterable_org_id(self):
        org = {"_id": 0, "organizationId": 362, "name": "Acme"}

        def fake_paginate_get(air_host, api_token, path, params=None, verbose=False):
            self.assertEqual(path, "/api/public/organizations")
            return [org]

        def fake_api_get(air_host, api_token, path, params=None):
            self.assertEqual(path, "/api/public/organizations/0")
            return FakeResponse(True, {"result": org})

        self.module.paginate_get = fake_paginate_get
        self.module.api_get = fake_api_get

        scope = self.module.resolve_org_scope("host", "token", 0)

        self.assertEqual(scope["resolvedOrgId"], "362")
        self.assertEqual(scope["candidateOrgIds"], ["362"])

    def test_case_lookup_uses_filterable_org_id(self):
        seen_org_ids = []

        def fake_paginate_get(air_host, api_token, path, params=None, verbose=False):
            self.assertEqual(path, "/api/public/cases")
            seen_org_ids.append(params["filter[organizationIds]"])
            return [
                {
                    "_id": "case-1",
                    "organizationId": 362,
                    "metadata": {"investigationId": "INV-1"},
                }
            ]

        self.module.paginate_get = fake_paginate_get

        case = self.module.get_case_by_investigation_id(
            "host",
            "token",
            "INV-1",
            ["362"],
        )

        self.assertEqual(case["_id"], "case-1")
        self.assertEqual(seen_org_ids, ["362"])


if __name__ == "__main__":
    unittest.main()
