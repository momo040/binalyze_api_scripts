import importlib
import unittest


class PolicyResolutionTests(unittest.TestCase):
    def test_case_acquire_resolves_policy_by_name(self):
        module = importlib.import_module("scripts.case_acquire")
        original_paginate_get = module.paginate_get

        def fake_paginate_get(air_host, api_token, path, params=None, verbose=False):
            self.assertEqual(path, "/api/public/policies")
            return [
                {"_id": "pol-1", "name": "Containment Policy"},
                {"_id": "pol-2", "name": "Triage Policy"},
            ]

        module.paginate_get = fake_paginate_get
        try:
            policy = module.resolve_policy(
                "host",
                "token",
                policy_name_value="Containment Policy",
            )
        finally:
            module.paginate_get = original_paginate_get

        self.assertEqual(policy["_id"], "pol-1")
        self.assertEqual(module.policy_filter_value(policy), "Containment Policy")

    def test_bulk_acquire_resolves_policy_by_id(self):
        module = importlib.import_module("scripts.investigation_acquire_from_csv")
        original_paginate_get = module.paginate_get

        def fake_paginate_get(air_host, api_token, path, params=None, verbose=False):
            self.assertEqual(path, "/api/public/policies")
            return [
                {"_id": "pol-1", "name": "Containment Policy"},
                {"_id": "pol-2", "name": "Triage Policy"},
            ]

        module.paginate_get = fake_paginate_get
        try:
            policy = module.resolve_policy(
                "host",
                "token",
                policy_id_value="pol-2",
            )
        finally:
            module.paginate_get = original_paginate_get

        self.assertEqual(policy["_id"], "pol-2")
        self.assertEqual(module.policy_filter_value(policy), "Triage Policy")


if __name__ == "__main__":
    unittest.main()
