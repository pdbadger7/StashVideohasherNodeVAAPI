import os
import tempfile
import unittest

import config
from helpers.generated_media import (
    cleanup_generated_staging_dirs,
    generated_media_path,
    prepare_generated_staging_dirs,
    transfer_generated_files,
)


class GeneratedMediaTests(unittest.TestCase):
    def setUp(self):
        self.original_translations = config.translations
        self.original_sprite_path = config.sprite_path
        self.original_preview_path = config.preview_path
        self.original_marker_path = config.marker_path

    def tearDown(self):
        config.translations = self.original_translations
        config.sprite_path = self.original_sprite_path
        config.preview_path = self.original_preview_path
        config.marker_path = self.original_marker_path

    def test_generated_media_path_uses_stash_generated_translation(self):
        config.translations = [{"orig": "/root/.stash/", "local": "/mnt/stash/.stash/"}]

        path = generated_media_path("/tmp/hasher/sprites", "vtt", "abc_sprite.jpg")

        self.assertEqual(path, "/mnt/stash/.stash/generated/vtt/abc_sprite.jpg")

    def test_generated_media_path_falls_back_to_staging_path_without_translation(self):
        config.translations = [{"orig": "/data/", "local": "/mnt/data/"}]

        path = generated_media_path("/tmp/hasher/sprites", "vtt", "abc_sprite.jpg")

        self.assertEqual(path, "/tmp/hasher/sprites/abc_sprite.jpg")

    def test_transfer_generated_files_moves_to_translated_stash_storage_and_keeps_staging_dir(self):
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
            self.assertTrue(os.path.exists(staging))

    def test_prepare_and_cleanup_generated_staging_dirs(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config.sprite_path = os.path.join(temp_dir, "hasher", "sprites")
            config.preview_path = os.path.join(temp_dir, "hasher", "previews")
            config.marker_path = os.path.join(temp_dir, "hasher", "markers")
            stash_mount = os.path.join(temp_dir, "stash")
            config.translations = [{"orig": "/root/.stash/", "local": stash_mount + os.sep}]

            prepare_generated_staging_dirs()

            self.assertTrue(os.path.isdir(config.sprite_path))
            self.assertTrue(os.path.isdir(config.preview_path))
            self.assertTrue(os.path.isdir(config.marker_path))

            cleanup_generated_staging_dirs()

            self.assertFalse(os.path.exists(config.sprite_path))
            self.assertFalse(os.path.exists(config.preview_path))
            self.assertFalse(os.path.exists(config.marker_path))


if __name__ == "__main__":
    unittest.main()
