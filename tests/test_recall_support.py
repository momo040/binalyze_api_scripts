import importlib
import unittest


class FakeResponse:
    def __init__(self, payload, ok=True, status_code=200):
        self._payload = payload
        self.ok = ok
        self.status_code = status_code
        self.text = str(payload)

    def json(self):
        return self._payload


class RecallSupportTests(unittest.TestCase):
    def test_case_acquire_parses_recall_mode_without_endpoint(self):
        module = importlib.import_module("scripts.case_acquire")

        args = module.parse_args(["0", "--recall-task-id", "TASK-123"])

        self.assertEqual(args["org_id"], "0")
        self.assertIsNone(args["endpoint"])
        self.assertEqual(args["recall_task_id"], "TASK-123")

    def test_case_acquire_cancel_task_posts_to_task_cancel_endpoint(self):
        module = importlib.import_module("scripts.case_acquire")
        original_api_post = module.api_post
        calls = []

        def fake_api_post(air_host, api_token, path, body=None, params=None):
            calls.append((path, body, params))
            return FakeResponse({"result": {"status": "cancelled"}})

        module.api_post = fake_api_post
        try:
            result = module.cancel_task("host", "token", "TASK-123")
        finally:
            module.api_post = original_api_post

        self.assertEqual(calls, [("/api/public/tasks/TASK-123/cancel", None, None)])
        self.assertTrue(result["ok"])
        self.assertEqual(result["statusCode"], 200)

    def test_bulk_collect_recall_targets_dedupes_task_ids(self):
        module = importlib.import_module("scripts.investigation_acquire_from_csv")

        targets = module.collect_recall_targets(
            {
                "launches": [
                    {
                        "rowNumber": 2,
                        "identifier": "asset-1",
                        "taskId": "TASK-1",
                        "asset": {"name": "asset-1"},
                    },
                    {
                        "rowNumber": 3,
                        "identifier": "asset-1-duplicate",
                        "taskId": "TASK-1",
                        "asset": {"name": "asset-1"},
                    },
                    {
                        "rowNumber": 4,
                        "identifier": "asset-2",
                        "taskId": "TASK-2",
                        "asset": {"name": "asset-2"},
                    },
                ]
            }
        )

        self.assertEqual(
            targets,
            [
                {
                    "taskId": "TASK-1",
                    "rowNumber": 2,
                    "identifier": "asset-1",
                    "asset": {"name": "asset-1"},
                },
                {
                    "taskId": "TASK-2",
                    "rowNumber": 4,
                    "identifier": "asset-2",
                    "asset": {"name": "asset-2"},
                },
            ],
        )

    def test_bulk_parse_args_accepts_recall_report_without_csv_or_case(self):
        module = importlib.import_module("scripts.investigation_acquire_from_csv")

        args = module.parse_args(["0", "--recall-report", "bulk_acquire_report.json"])

        self.assertEqual(args.org_id, "0")
        self.assertIsNone(args.csv_path)
        self.assertEqual(args.recall_report, "bulk_acquire_report.json")


if __name__ == "__main__":
    unittest.main()
