import unittest

from helpers.preview_video_generator import PreviewVideoGenerator


def make_generator(skip_seconds=15, clip_length=1, preview_clips=15):
    return PreviewVideoGenerator(
        "tests/test.mp4",
        "/tmp/preview.mp4",
        "testhash",
        preview_clips=preview_clips,
        clip_length=clip_length,
        skip_seconds=skip_seconds,
    )


class PreviewVideoGeneratorTests(unittest.TestCase):
    def test_short_video_reduces_skip_seconds_for_preview_start_times(self):
        generator = make_generator(skip_seconds=15, clip_length=1, preview_clips=15)

        start_times = generator.get_start_times(15.0)

        self.assertEqual(len(start_times), 15)
        self.assertGreater(start_times[0], 0)
        self.assertLess(start_times[-1], 14.0)

    def test_video_shorter_than_clip_uses_full_video_start(self):
        generator = make_generator(skip_seconds=15, clip_length=1, preview_clips=15)

        self.assertEqual(generator.get_start_times(0.5), [0.0])

    def test_long_enough_video_keeps_configured_skip_seconds(self):
        generator = make_generator(skip_seconds=15, clip_length=1, preview_clips=15)

        start_times = generator.get_start_times(20.0)

        self.assertEqual(len(start_times), 15)
        self.assertGreater(start_times[0], 15.0)


if __name__ == "__main__":
    unittest.main()
