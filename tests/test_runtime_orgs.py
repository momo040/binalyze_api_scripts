import unittest

from lib.runtime import (
    organization_candidate_ids,
    organization_display_id,
    organization_filter_id,
    organization_matches_identifier,
    unique_filterable_organization_ids,
)


class RuntimeOrganizationIdTests(unittest.TestCase):
    def test_prefers_organization_id_over_zero_root_id(self):
        org = {"_id": 0, "organizationId": 362, "name": "Acme"}
        self.assertEqual(organization_filter_id(org), "362")
        self.assertEqual(organization_display_id(org), "362")

    def test_prefers_non_zero_id_when_organization_id_missing(self):
        org = {"_id": "0", "id": "362", "name": "Acme"}
        self.assertEqual(organization_filter_id(org), "362")
        self.assertEqual(organization_display_id(org), "362")

    def test_uses_only_non_zero_candidate_when_available(self):
        org = {"_id": "", "id": None, "organizationId": 144}
        self.assertEqual(organization_candidate_ids(org), ["144"])
        self.assertEqual(organization_filter_id(org), "144")

    def test_returns_zero_only_when_no_better_candidate_exists(self):
        org = {"_id": 0, "id": "", "organizationId": None}
        self.assertEqual(organization_filter_id(org), "0")
        self.assertEqual(organization_display_id(org), "0")

    def test_unique_filterable_ids_skip_zero_like_values(self):
        orgs = [
            {"_id": 0, "organizationId": 362},
            {"_id": "0", "id": "362"},
            {"_id": 0},
            {"organizationId": 481},
        ]
        self.assertEqual(unique_filterable_organization_ids(orgs), ["362", "481"])

    def test_matches_requested_org_against_any_known_identifier(self):
        org = {"_id": 0, "id": 77, "organizationId": 362}
        self.assertTrue(organization_matches_identifier(org, "0"))
        self.assertTrue(organization_matches_identifier(org, "77"))
        self.assertTrue(organization_matches_identifier(org, "362"))
        self.assertFalse(organization_matches_identifier(org, "999"))


if __name__ == "__main__":
    unittest.main()
