"""Regression coverage for completed-date detection; no live AWS calls."""
import os
import unittest
from unittest.mock import Mock, patch

import main
import daily_aggregator_handler as aggregator


class BackfillDateTests(unittest.TestCase):
    def test_completed_date_with_device_underscores(self):
        self.assert_completed("CLONE_TEST_DEVICE_2010-10-02_Shimmer_CLONE_combined.json")

    def test_original_device_filename(self):
        self.assert_completed("device_2010-10-02_Shimmer_CLONE_combined.json")

    def assert_completed(self, filename):
        table = Mock()
        table.scan.return_value = {"Items": [{"recordedTimestamp": "2010-10-02T12:00:00+00:00"}]}
        resource = Mock()
        resource.Table.return_value = table
        objects = {"Contents": [{"Key": "combinedbyDay/" + filename}]}
        with patch.dict(os.environ, {"DDB_FILE_TABLE": "test-metadata"}), \
                patch.object(main.boto3, "resource", return_value=resource), \
                patch.object(main.s3_client, "list_objects_v2", return_value=objects), \
                patch.object(aggregator, "lambda_handler") as handler:
            result = main.backfill_missing_dates(limit=5)
        self.assertEqual(result["processed_dates_list"], ["2010-10-02"])
        self.assertEqual(result["missing_dates"], [])
        handler.assert_not_called()


if __name__ == "__main__":
    unittest.main()
