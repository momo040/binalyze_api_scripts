import importlib
import unittest


class ProfileListOrgIdTests(unittest.TestCase):
    def test_bulk_acquire_profile_lookup_includes_org_id(self):
        module = importlib.import_module("scripts.investigation_acquire_from_csv")
        original_paginate_get = module.paginate_get
        calls = []

        def fake_paginate_get(air_host, api_token, path, params=None, verbose=False):
            calls.append((path, params))
            return []

        module.paginate_get = fake_paginate_get
        try:
            module.list_profiles("host", "token", 0)
        finally:
            module.paginate_get = original_paginate_get

        self.assertEqual(
            calls,
            [
                (
                    "/api/public/acquisitions/profiles",
                    {"organizationId": "0", "filter[organizationIds]": "0"},
                )
            ],
        )

    def test_case_acquire_profile_lookup_includes_org_id(self):
        module = importlib.import_module("scripts.case_acquire")
        original_paginate_get = module.paginate_get
        calls = []

        def fake_paginate_get(air_host, api_token, path, params=None, verbose=False):
            calls.append((path, params))
            return []

        module.paginate_get = fake_paginate_get
        try:
            module.list_profiles("host", "token", 0)
        finally:
            module.paginate_get = original_paginate_get

        self.assertEqual(
            calls,
            [
                (
                    "/api/public/acquisitions/profiles",
                    {"organizationId": "0", "filter[organizationIds]": "0"},
                )
            ],
        )


if __name__ == "__main__":
    unittest.main()
