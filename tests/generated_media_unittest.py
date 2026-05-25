import os
import tempfile
import unittest

import config
from helpers.generated_media import generated_media_path, transfer_generated_files


class GeneratedMediaTests(unittest.TestCase):
    def setUp(self):
        self.original_translations = config.translations

    def tearDown(self):
        config.translations = self.original_translations

    def test_generated_media_path_uses_stash_generated_translation(self):
        config.translations = [{"orig": "/root/.stash/", "local": "/mnt/stash/.stash/"}]

        path = generated_media_path("/tmp/hasher/sprites", "vtt", "abc_sprite.jpg")

        self.assertEqual(path, "/mnt/stash/.stash/generated/vtt/abc_sprite.jpg")

    def test_generated_media_path_falls_back_to_staging_path_without_translation(self):
        config.translations = [{"orig": "/data/", "local": "/mnt/data/"}]

        path = generated_media_path("/tmp/hasher/sprites", "vtt", "abc_sprite.jpg")

        self.assertEqual(path, "/tmp/hasher/sprites/abc_sprite.jpg")

    def test_transfer_generated_files_moves_to_translated_stash_storage_and_cleans_staging(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            staging = os.path.join(temp_dir, "hasher", "sprites")
            stash_mount = os.path.join(temp_dir, "stash")
            os.makedirs(staging)
            source = os.path.join(staging, "abc_sprite.jpg")
            with open(source, "w", encoding="utf-8") as handle:
                handle.write("sprite")

            config.translations = [{"orig": "/root/.stash/", "local": stash_mount + os.sep}]

            final_paths = transfer_generated_files([source], staging, "vtt")

            expected = os.path.join(stash_mount, "generated", "vtt", "abc_sprite.jpg")
            self.assertEqual(final_paths, [expected])
            self.assertFalse(os.path.exists(source))
            self.assertTrue(os.path.exists(expected))
            self.assertFalse(os.path.exists(staging))


if __name__ == "__main__":
    unittest.main()
