import unittest

from scripts.version_utils import (
    bump_minor_version,
    extract_project_version,
    replace_project_version,
)


class VersionUtilsTests(unittest.TestCase):
    def test_bump_minor_version_resets_patch(self):
        self.assertEqual(bump_minor_version("0.1.7"), "0.2.0")

    def test_extract_project_version(self):
        content = """
[project]
name = "StashVideoHasherNode"
version = "1.4.9"
"""
        self.assertEqual(extract_project_version(content), "1.4.9")

    def test_replace_project_version(self):
        content = """
[project]
name = "StashVideoHasherNode"
version = "1.4.9"
"""
        updated = replace_project_version(content, "1.5.0")
        self.assertIn('version = "1.5.0"', updated)


if __name__ == "__main__":
    unittest.main()
