import importlib
import unittest


class FakeResponse:
    def __init__(self, payload, ok=True, status_code=200):
        self._payload = payload
        self.ok = ok
        self.status_code = status_code

    def json(self):
        return self._payload


class PolicyResolutionTests(unittest.TestCase):
    def test_case_acquire_resolves_policy_by_name(self):
        module = importlib.import_module("scripts.case_acquire")
        original_paginate_get = module.paginate_get
        original_api_get = module.api_get

        def fake_paginate_get(air_host, api_token, path, params=None, verbose=False):
            self.assertEqual(path, "/api/public/policies")
            self.assertEqual(params, {"filter[organizationIds]": "0"})
            return [
                {"_id": "pol-1", "name": "Containment Policy"},
                {"_id": "pol-2", "name": "Triage Policy"},
            ]

        def fake_api_get(air_host, api_token, path, params=None):
            self.assertEqual(path, "/api/public/policies/pol-1")
            self.assertEqual(params, {"filter[organizationIds]": "0"})
            return FakeResponse(
                {
                    "result": {
                        "_id": "pol-1",
                        "name": "Containment Policy",
                        "taskConfig": {"choice": "use-policy-options"},
                    }
                }
            )

        module.paginate_get = fake_paginate_get
        module.api_get = fake_api_get
        try:
            policy = module.resolve_policy(
                "host",
                "token",
                0,
                policy_name_value="Containment Policy",
            )
        finally:
            module.paginate_get = original_paginate_get
            module.api_get = original_api_get

        self.assertEqual(policy["_id"], "pol-1")
        self.assertEqual(policy["taskConfig"]["choice"], "use-policy-options")
        self.assertEqual(module.policy_filter_value(policy), "Containment Policy")

    def test_bulk_acquire_resolves_policy_by_id(self):
        module = importlib.import_module("scripts.investigation_acquire_from_csv")
        original_paginate_get = module.paginate_get
        original_api_get = module.api_get

        def fake_paginate_get(air_host, api_token, path, params=None, verbose=False):
            self.assertEqual(path, "/api/public/policies")
            self.assertEqual(params, {"filter[organizationIds]": "0"})
            return [
                {"_id": "pol-1", "name": "Containment Policy"},
                {"_id": "pol-2", "name": "Triage Policy"},
            ]

        def fake_api_get(air_host, api_token, path, params=None):
            self.assertEqual(path, "/api/public/policies/pol-2")
            self.assertEqual(params, {"filter[organizationIds]": "0"})
            return FakeResponse(
                {
                    "result": {
                        "_id": "pol-2",
                        "name": "Triage Policy",
                        "droneConfig": {"enabled": True},
                    }
                }
            )

        module.paginate_get = fake_paginate_get
        module.api_get = fake_api_get
        try:
            policy = module.resolve_policy(
                "host",
                "token",
                0,
                policy_id_value="pol-2",
            )
        finally:
            module.paginate_get = original_paginate_get
            module.api_get = original_api_get

        self.assertEqual(policy["_id"], "pol-2")
        self.assertTrue(policy["droneConfig"]["enabled"])
        self.assertEqual(module.policy_filter_value(policy), "Triage Policy")


if __name__ == "__main__":
    unittest.main()
