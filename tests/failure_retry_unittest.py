import importlib
import sys
import unittest
from unittest.mock import Mock, patch

import config


class FailureRetryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with patch("stashapi.stashapp.StashInterface", return_value=Mock()):
            sys.modules.pop("helpers.stash_utils", None)
            cls.stash_utils = importlib.import_module("helpers.stash_utils")

    def setUp(self):
        self.original_dry_run = config.dry_run
        self.original_hashing_tag = config.hashing_tag
        self.original_error_log_path = config.error_log_path
        self.original_excluded_paths = config.excluded_paths
        self.original_filemask = config.filemask
        self.original_failed = set(self.stash_utils.failed_scene_ids_this_run)
        self.stash_utils.failed_scene_ids_this_run.clear()

    def tearDown(self):
        config.dry_run = self.original_dry_run
        config.hashing_tag = self.original_hashing_tag
        config.error_log_path = self.original_error_log_path
        config.excluded_paths = self.original_excluded_paths
        config.filemask = self.original_filemask
        self.stash_utils.failed_scene_ids_this_run.clear()
        self.stash_utils.failed_scene_ids_this_run.update(self.original_failed)

    def test_tag_scene_error_suppresses_retry_even_when_stash_update_fails(self):
        config.dry_run = False
        config.hashing_tag = 10

        self.stash_utils.stash.update_scenes.side_effect = RuntimeError("api down")
        tagged = self.stash_utils.tag_scene_error("8320", 11)

        self.assertFalse(tagged)
        self.assertTrue(self.stash_utils.is_scene_failed_this_run("8320"))

    def test_total_count_excludes_scenes_failed_in_this_run(self):
        config.excluded_paths = []
        config.filemask = None
        self.stash_utils.mark_scene_failed_this_run("8320")

        scenes = [
            {"id": "8320", "files": [{"path": "/data/a.mp4"}]},
            {"id": "8321", "files": [{"path": "/data/b.mp4"}]},
        ]
        self.stash_utils.stash.find_scenes.return_value = scenes

        total = self.stash_utils.get_total_scene_count()

        self.assertEqual(total, 1)


if __name__ == "__main__":
    unittest.main()
