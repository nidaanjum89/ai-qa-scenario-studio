import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import memory_store
from generator import build_artifacts


class MemoryStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_patch = patch.object(memory_store, "DB_PATH", Path(self.temp_dir.name) / "test-memory.sqlite3")
        self.db_patch.start()
        self.project = memory_store.create_project("Shop QA")
        self.payload = {
            "projectId": self.project["id"],
            "product": "Sample Shop",
            "url": "https://example.test/",
            "feature": "Checkout",
            "story": "As a shopper, I want to place an order.",
            "criteria": ["AC-01 | A valid order shows a confirmation."],
        }
        self.result = build_artifacts(self.payload)

    def tearDown(self):
        self.db_patch.stop()
        self.temp_dir.cleanup()

    def test_saved_plan_can_be_opened_after_new_database_connection(self):
        saved = memory_store.save_run(self.project["id"], self.payload, self.result)
        opened = memory_store.get_run(saved["runId"])
        self.assertEqual(opened["payload"]["story"], self.payload["story"])
        self.assertEqual(opened["result"]["coverage"], 100)
        self.assertEqual(opened["version"], 1)

    def test_only_approved_scenarios_are_project_memory(self):
        saved = memory_store.save_run(self.project["id"], self.payload, self.result)
        self.assertEqual(memory_store.approved_examples(self.project["id"]), [])
        memory_store.save_reviews(saved["runId"], {"AC-01": "approved"})
        examples = memory_store.approved_examples(self.project["id"])
        self.assertEqual(len(examples), 1)
        self.assertEqual(examples[0]["criteria"][0]["id"], "AC-01")

    def test_project_export_and_import_keep_plans_and_reviews(self):
        saved = memory_store.save_run(self.project["id"], self.payload, self.result)
        memory_store.save_reviews(saved["runId"], {"AC-01": "approved"})
        bundle = memory_store.export_project(self.project["id"])
        imported = memory_store.import_project(bundle)
        imported_runs = memory_store.list_runs(imported["id"])
        self.assertEqual(imported_runs[0]["feature"], "Checkout")
        restored = memory_store.get_run(imported_runs[0]["runId"])
        self.assertEqual(restored["reviews"]["AC-01"], "approved")


if __name__ == "__main__":
    unittest.main()
