#!/usr/bin/env python3
"""Compare reference (temp-BMP) and optimized (pipe-BMP) pHash outputs."""

import argparse
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from PIL import Image

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import config
from helpers import phash_generator

VIDEO_EXTENSIONS = {
    ".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv", ".webm", ".m4v", ".mpg", ".mpeg"
}


def _reference_extract_frame_software(video_path, timestamp):
    with tempfile.NamedTemporaryFile(suffix=".bmp", delete=False) as tmp_file:
        tmp = tmp_file.name
    try:
        subprocess.run(
            [
                config.ffmpeg,
                "-ss",
                f"{timestamp:.6f}",
                "-i",
                video_path,
                "-frames:v",
                "1",
                "-vf",
                f"scale={phash_generator.FRAME_WIDTH}:-1",
                "-y",
                "-loglevel",
                "error",
                tmp,
            ],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=60,
        )
        img = Image.open(tmp)
        return img.copy()
    except subprocess.CalledProcessError as e:
        err = e.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"ffmpeg frame extraction failed at {timestamp:.1f}s: {err}") from e
    finally:
        Path(tmp).unlink(missing_ok=True)


def _reference_extract_frame_vaapi(video_path, timestamp, vaapi_device):
    with tempfile.NamedTemporaryFile(suffix=".bmp", delete=False) as tmp_file:
        tmp = tmp_file.name
    try:
        subprocess.run(
            [
                config.ffmpeg,
                "-vaapi_device",
                vaapi_device,
                "-hwaccel",
                "vaapi",
                "-hwaccel_output_format",
                "vaapi",
                "-ss",
                f"{timestamp:.6f}",
                "-i",
                video_path,
                "-frames:v",
                "1",
                "-vf",
                f"scale_vaapi={phash_generator.FRAME_WIDTH}:-1,hwdownload,format=bgr0",
                "-y",
                "-loglevel",
                "error",
                tmp,
            ],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=60,
        )
        img = Image.open(tmp)
        return img.copy()
    except Exception:
        return _reference_extract_frame_software(video_path, timestamp)
    finally:
        Path(tmp).unlink(missing_ok=True)


def _reference_extract_frame(video_path, timestamp, vaapi_device=None):
    if vaapi_device:
        return _reference_extract_frame_vaapi(video_path, timestamp, vaapi_device)
    return _reference_extract_frame_software(video_path, timestamp)


def _reference_build_sprite(video_path, duration, vaapi_device=None):
    offset = 0.05 * duration
    step_size = (0.90 * duration) / phash_generator.FRAME_COUNT

    frames = []
    for i in range(phash_generator.FRAME_COUNT):
        ts = offset + i * step_size
        frame = _reference_extract_frame(video_path, ts, vaapi_device=vaapi_device)
        if frame is None:
            frame = Image.new("RGB", (phash_generator.FRAME_WIDTH, phash_generator.FRAME_WIDTH), (0, 0, 0))
        frames.append(frame)

    frame_w = frames[0].width
    frame_h = frames[0].height
    sprite = Image.new(
        "RGB",
        (phash_generator.COLUMNS * frame_w, phash_generator.ROWS * frame_h),
    )

    for i, frame in enumerate(frames):
        if frame.width != frame_w or frame.height != frame_h:
            frame = frame.resize((frame_w, frame_h), Image.BILINEAR)
        sprite.paste(frame, ((i % phash_generator.COLUMNS) * frame_w, (i // phash_generator.COLUMNS) * frame_h))

    return sprite


def _reference_compute_phash(video_path, vaapi_device=None):
    duration = phash_generator._get_duration(video_path)
    if duration <= 0:
        raise RuntimeError(f"Invalid video duration ({duration}s) for {video_path}")
    sprite = _reference_build_sprite(video_path, duration, vaapi_device=vaapi_device)
    phash = phash_generator._phash_from_sprite(sprite)
    return {"phash": phash}


def _collect_videos(root):
    return sorted(
        p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in VIDEO_EXTENSIONS
    )


def _ffmpeg_version():
    result = subprocess.run(
        [config.ffmpeg, "-version"],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=15,
    )
    return result.stdout.decode("utf-8", errors="replace").splitlines()[0].strip()


def _timed_hash(fn, video_path, vaapi_device=None):
    start = time.perf_counter()
    output = fn(video_path, vaapi_device=vaapi_device)
    elapsed = time.perf_counter() - start
    return output["phash"], elapsed


def _speedup(old_s, new_s):
    if new_s == 0:
        return "inf"
    return f"{old_s / new_s:.3f}x"


def _print_result(mode, file_path, old_hash, new_hash, old_s, new_s):
    match = "match" if old_hash == new_hash else "MISMATCH"
    print(
        f"[{mode}] {file_path} | old={old_hash} new={new_hash} "
        f"| {match} | old_s={old_s:.3f} new_s={new_s:.3f} speedup={_speedup(old_s, new_s)}"
    )


def _run_mode(videos, vaapi_device=None):
    mode = "vaapi" if vaapi_device else "software"
    mismatches = 0
    failures = 0
    for path in videos:
        video = str(path)
        try:
            old_hash, old_s = _timed_hash(_reference_compute_phash, video, vaapi_device=vaapi_device)
            new_hash, new_s = _timed_hash(phash_generator.compute_phash, video, vaapi_device=vaapi_device)
            _print_result(mode, video, old_hash, new_hash, old_s, new_s)
            if old_hash != new_hash:
                mismatches += 1
        except Exception as exc:
            failures += 1
            print(f"[{mode}] {video} | ERROR | {exc}", file=sys.stderr)
    return mismatches, failures


def main():
    parser = argparse.ArgumentParser(
        description="Compare reference temp-BMP pHash path against current implementation."
    )
    parser.add_argument("videos_dir", type=Path, help="Directory containing sample videos.")
    parser.add_argument(
        "--vaapi-device",
        default=None,
        help="Optional VAAPI render node (e.g. /dev/dri/renderD128).",
    )
    parser.add_argument(
        "--ffmpeg-bin",
        default=None,
        help="Optional ffmpeg binary path override.",
    )
    parser.add_argument(
        "--ffprobe-bin",
        default=None,
        help="Optional ffprobe binary path override.",
    )
    args = parser.parse_args()

    if args.ffmpeg_bin:
        config.ffmpeg = args.ffmpeg_bin
    if args.ffprobe_bin:
        config.ffprobe = args.ffprobe_bin

    if not args.videos_dir.exists() or not args.videos_dir.is_dir():
        print(f"videos_dir does not exist or is not a directory: {args.videos_dir}", file=sys.stderr)
        return 2

    videos = _collect_videos(args.videos_dir)
    if not videos:
        print(f"No video files found under: {args.videos_dir}", file=sys.stderr)
        return 2

    try:
        ffmpeg_version = _ffmpeg_version()
    except FileNotFoundError as exc:
        print(f"ffmpeg binary not found: {exc}", file=sys.stderr)
        return 2

    print(f"ffmpeg_version: {ffmpeg_version}")
    print(f"files_found: {len(videos)}")

    sw_mismatch, sw_fail = _run_mode(videos, vaapi_device=None)
    total_mismatch = sw_mismatch
    total_fail = sw_fail

    if args.vaapi_device:
        va_mismatch, va_fail = _run_mode(videos, vaapi_device=args.vaapi_device)
        total_mismatch += va_mismatch
        total_fail += va_fail

    print(
        f"summary | mismatches={total_mismatch} failures={total_fail} "
        f"modes={'software+vaapi' if args.vaapi_device else 'software'}"
    )

    if total_mismatch or total_fail:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
