import unittest

from lib.runtime import build_acquisition_request


class AcquisitionRequestBodyTests(unittest.TestCase):
    def test_builds_acquire_body_with_default_policies(self):
        body = build_acquisition_request(
            case_id="C-2022-0001",
            acquisition_profile_id="full",
            endpoint_id="0ccbb181-685c-4f1e-982a-6f7c7e88eadd",
            org_id="0",
            policy="Containment Policy",
        )

        self.assertEqual(body["caseId"], "C-2022-0001")
        self.assertEqual(body["acquisitionProfileId"], "full")
        self.assertEqual(
            body["filter"]["includedEndpointIds"],
            ["0ccbb181-685c-4f1e-982a-6f7c7e88eadd"],
        )
        self.assertEqual(body["filter"]["organizationIds"], [0])
        self.assertEqual(body["filter"]["policy"], "Containment Policy")
        self.assertFalse(body["droneConfig"]["enabled"])
        self.assertFalse(body["droneConfig"]["mitreEnabled"])
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

    def test_merges_policy_task_and_drone_config_into_acquire_body(self):
        body = build_acquisition_request(
            case_id="C-2022-0001",
            acquisition_profile_id="full",
            endpoint_id="0ccbb181-685c-4f1e-982a-6f7c7e88eadd",
            org_id="0",
            policy="Containment Policy",
            policy_data={
                "_id": "pol-1",
                "name": "Containment Policy",
                "configuration": {
                    "taskConfig": {
                        "choice": "use-policy-options",
                        "cpu": {"limit": 55},
                        "compression": {
                            "enabled": False,
                            "encryption": {
                                "enabled": True,
                                "password": "secret",
                            },
                        },
                    },
                    "droneConfig": {
                        "enabled": True,
                        "mitreEnabled": True,
                        "keywords": ["keyword-1", "keyword-2"],
                    },
                },
            },
        )

        self.assertEqual(body["taskConfig"]["choice"], "use-policy-options")
        self.assertEqual(body["taskConfig"]["cpu"]["limit"], 55)
        self.assertFalse(body["taskConfig"]["compression"]["enabled"])
        self.assertTrue(body["taskConfig"]["compression"]["encryption"]["enabled"])
        self.assertEqual(
            body["taskConfig"]["compression"]["encryption"]["password"],
            "secret",
        )
        self.assertEqual(
            body["taskConfig"]["saveTo"]["windows"]["path"],
            "Binalyze\\AIR\\",
        )
        self.assertTrue(body["droneConfig"]["enabled"])
        self.assertTrue(body["droneConfig"]["mitreEnabled"])
        self.assertEqual(body["droneConfig"]["keywords"], ["keyword-1", "keyword-2"])
        self.assertEqual(body["droneConfig"]["analyzers"], ["bha", "wsa", "aa", "ara"])

    def test_filters_mitre_attack_analyzers_from_drone_config(self):
        body = build_acquisition_request(
            case_id="C-2022-0001",
            acquisition_profile_id="full",
            endpoint_id="0ccbb181-685c-4f1e-982a-6f7c7e88eadd",
            org_id="0",
            policy_data={
                "droneConfig": {
                    "enabled": True,
                    "mitreEnabled": True,
                    "analyzers": [
                        "bha",
                        "mitre-attack",
                        "yara-memory",
                        "wsa",
                    ],
                }
            },
        )

        self.assertTrue(body["droneConfig"]["enabled"])
        self.assertTrue(body["droneConfig"]["mitreEnabled"])
        self.assertEqual(body["droneConfig"]["analyzers"], ["bha", "mitre-attack", "wsa"])


if __name__ == "__main__":
    unittest.main()
