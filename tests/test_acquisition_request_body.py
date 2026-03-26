import unittest

from lib.runtime import build_acquisition_request


class AcquisitionRequestBodyTests(unittest.TestCase):
    def test_builds_acquire_body_with_default_policies(self):
        body = build_acquisition_request(
            case_id="C-2022-0001",
            acquisition_profile_id="full",
            endpoint_id="0ccbb181-685c-4f1e-982a-6f7c7e88eadd",
            org_id="0",
        )

        self.assertEqual(body["caseId"], "C-2022-0001")
        self.assertEqual(body["acquisitionProfileId"], "full")
        self.assertEqual(
            body["filter"]["includedEndpointIds"],
            ["0ccbb181-685c-4f1e-982a-6f7c7e88eadd"],
        )
        self.assertEqual(body["filter"]["organizationIds"], [0])
        self.assertEqual(body["droneConfig"]["analyzers"], ["bha", "wsa", "aa", "ara"])
        self.assertEqual(body["droneConfig"]["keywords"], [])
        self.assertEqual(body["taskConfig"]["choice"], "use-custom-options")
        self.assertEqual(body["taskConfig"]["cpu"]["limit"], 80)
        self.assertTrue(body["taskConfig"]["compression"]["enabled"])
        self.assertFalse(body["taskConfig"]["compression"]["encryption"]["enabled"])
        self.assertEqual(
            body["taskConfig"]["saveTo"]["windows"]["path"],
            "Binalyze\\AIR\\",
        )
        self.assertEqual(body["filter"]["excludedEndpointIds"], [])
        self.assertEqual(body["filter"]["searchTerm"], "")


if __name__ == "__main__":
    unittest.main()
