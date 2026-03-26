import importlib
import unittest


class ValidationProgressTests(unittest.TestCase):
    def test_progress_message_includes_status_context(self):
        module = importlib.import_module("scripts.investigation_acquire_from_csv")

        message = module.build_validation_progress_message(
            processed=25,
            total=100,
            status_counts={
                "matched": 20,
                "missing": 2,
                "ambiguous": 1,
                "blank": 1,
                "duplicate_skipped": 1,
            },
            elapsed_seconds=125,
            current_identifier="WORKSTATION-01",
            api_lookups=18,
            cache_hits=7,
        )

        self.assertIn("25/100", message)
        self.assertIn("elapsed=02:05", message)
        self.assertIn("matched=20", message)
        self.assertIn("missing=2", message)
        self.assertIn("ambiguous=1", message)
        self.assertIn("blank=1", message)
        self.assertIn("dup=1", message)
        self.assertIn("lookups=18", message)
        self.assertIn("cache=7", message)
        self.assertIn("current=WORKSTATION-01", message)

    def test_progress_message_shortens_long_identifiers(self):
        module = importlib.import_module("scripts.investigation_acquire_from_csv")

        message = module.build_validation_progress_message(
            processed=1,
            total=1,
            status_counts={},
            elapsed_seconds=3,
            current_identifier="A" * 40,
            api_lookups=1,
            cache_hits=0,
        )

        self.assertIn("current=AAAAAAAAAAAAAAAAAAAAAAAAAAAAA...", message)


if __name__ == "__main__":
    unittest.main()
