# preview_video_generator.py

import subprocess
import os
import shutil
from tqdm import tqdm
from concurrent.futures import ThreadPoolExecutor
from config import verbose, nvenc, max_workers
import time
from datetime import datetime
from helpers.videotoolbox_utils import get_videotoolbox_encoder, normalize_videotoolbox_codec

class PreviewVideoGenerator:
    def __init__(self, filename, output_path, filehash, ffmpeg='ffmpeg', ffprobe='ffprobe',
                 preview_clips=15, clip_length=1, skip_seconds=0, include_audio=True,
                 scene_id=None, scene_name=None, use_vaapi=None, vaapi_device=None,
                 use_videotoolbox=None, videotoolbox_codec='h264'):
        self.filename = os.path.abspath(filename.strip('"').strip("'"))
        self.output_path = os.path.abspath(output_path)
        self.temp_dir = os.path.abspath(os.path.join(".tmp", f"preview_temp_{filehash}"))
        self.num_clips = preview_clips
        self.clip_length = clip_length
        self.skip_seconds = skip_seconds
        self.include_audio = include_audio
        self.ffmpeg = ffmpeg
        self.ffprobe = ffprobe
        self.scene_id = scene_id
        self.scene_name = scene_name
        self.use_vaapi = use_vaapi
        self.vaapi_device = vaapi_device
        self.use_videotoolbox = use_videotoolbox
        self.videotoolbox_codec = normalize_videotoolbox_codec(videotoolbox_codec)
        self.videotoolbox_encoder = get_videotoolbox_encoder(self.videotoolbox_codec)

    def get_video_duration(self):
        result = subprocess.run(
            [self.ffprobe, '-v', 'error', '-show_entries', 'format=duration',
             '-of', 'default=noprint_wrappers=1:nokey=1', self.filename],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        try:
            return float(result.stdout.strip())
        except (ValueError, TypeError):
            err = result.stderr.decode('utf-8', errors='replace').strip()
            raise RuntimeError(f"Could not determine duration for {self.filename}: {err}")

    def clean_previous_clips(self):
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def generate_clips(self):
        os.makedirs(self.temp_dir, exist_ok=True)
        video_duration = self.get_video_duration()
        start_times = self.get_start_times(video_duration)
        use_vaapi = bool(self.use_vaapi) and bool(self.vaapi_device)
        use_videotoolbox = bool(self.use_videotoolbox)

        def extract_clip(i, start_time):
            clip_file = os.path.join(self.temp_dir, f"clip_{i:03d}.mp4")
            audio_args = ['-c:a', 'aac', '-b:a', '192k'] if self.include_audio else ['-an']
            clip_uses_videotoolbox = False
            if use_vaapi:
                command = [self.ffmpeg,
                    '-vaapi_device', self.vaapi_device,
                    '-ss', str(start_time),
                    '-i', self.filename,
                    '-t', str(self.clip_length),
                    '-vf', 'format=nv12,hwupload,scale_vaapi=640:360',
                    '-c:v', 'h264_vaapi',
                    '-global_quality', '18',
                ] + audio_args + ['-y', '-loglevel', 'quiet', clip_file]
            elif nvenc:
                command = [self.ffmpeg,
                    '-ss', str(start_time),
                    '-i', self.filename,
                    '-t', str(self.clip_length),
                    '-s', '640x360',
                    '-c:v', 'h264_nvenc',
                    '-cq:v', '18',
                    '-preset', 'p4',
                ] + audio_args + ['-y', '-loglevel', 'quiet', clip_file]
            elif use_videotoolbox:
                clip_uses_videotoolbox = True
                command = [self.ffmpeg,
                    '-ss', str(start_time),
                    '-i', self.filename,
                    '-t', str(self.clip_length),
                    '-vf', 'scale=640:360',
                    '-c:v', self.videotoolbox_encoder,
                    '-b:v', '2500k',
                ] + audio_args + ['-y', '-loglevel', 'quiet', clip_file]
            else:
                command = [self.ffmpeg,
                    '-ss', str(start_time),
                    '-i', self.filename,
                    '-t', str(self.clip_length),
                    '-s', '640x360',
                    '-c:v', 'libx264',
                    '-crf', '18',
                    '-preset', 'slow',
                ] + audio_args + ['-y', '-loglevel', 'quiet', clip_file]
            try:
                subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            except subprocess.CalledProcessError as e:
                if clip_uses_videotoolbox:
                    print(f"⚠️ VideoToolbox ({self.videotoolbox_encoder}) failed for clip {i}; falling back to software (libx264).")
                    fallback_command = [self.ffmpeg,
                        '-ss', str(start_time),
                        '-i', self.filename,
                        '-t', str(self.clip_length),
                        '-s', '640x360',
                        '-c:v', 'libx264',
                        '-crf', '18',
                        '-preset', 'slow',
                    ] + audio_args + ['-y', '-loglevel', 'quiet', clip_file]
                    try:
                        subprocess.run(fallback_command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                        return clip_file
                    except subprocess.CalledProcessError as fallback_error:
                        fallback_stderr = fallback_error.stderr.decode('utf-8', errors='replace').strip().splitlines()
                        fallback_detail = fallback_stderr[-1] if fallback_stderr else str(fallback_error)
                        print(f"❌ Software fallback failed for clip {i} for scene {self.scene_id} — {self.scene_name}: {fallback_detail}")
                        return None
                stderr = e.stderr.decode('utf-8', errors='replace').strip().splitlines()
                detail = stderr[-1] if stderr else str(e)
                print(f"❌ Failed to generate clip {i} for scene {self.scene_id} — {self.scene_name}: {detail}")
                return None
            return clip_file

        clips = []
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [executor.submit(extract_clip, i, start_time) for i, start_time in enumerate(start_times)]
            iterator = tqdm(futures, desc="🎞️ Generating Preview Clips", unit="clip") if verbose else futures
            for future in iterator:
                clip = future.result()
                if clip:
                    clips.append(clip)

        return clips

    def get_start_times(self, video_duration):
        if video_duration <= 0:
            raise RuntimeError(f"Video duration must be positive, got {video_duration:.1f}s")

        if video_duration <= self.clip_length:
            if verbose and self.skip_seconds:
                print(
                    f"⚠️ Video too short ({video_duration:.1f}s) for skip_seconds={self.skip_seconds}; using full video for preview"
                )
            return [0.0]

        effective_skip_seconds = self.skip_seconds
        usable = video_duration - effective_skip_seconds - self.clip_length
        if usable <= 0:
            effective_skip_seconds = 0
            usable = video_duration - self.clip_length
            if verbose and self.skip_seconds:
                print(
                    f"⚠️ Video too short ({video_duration:.1f}s) for skip_seconds={self.skip_seconds}; using skip_seconds=0 for preview"
                )

        interval = usable / (self.num_clips + 1)
        return [effective_skip_seconds + interval * i for i in range(1, self.num_clips + 1)]

    def concatenate_clips(self, clips):
        missing = [clip for clip in clips if not os.path.exists(clip)]
        if missing:
            raise FileNotFoundError(f"Missing clips: {missing}")

        concat_file = os.path.join(self.temp_dir, "clips.txt")
        with open(concat_file, 'w') as f:
            for clip in sorted(clips):
                safe_path = os.path.normpath(clip).replace("\\", "/")
                f.write(f"file '{safe_path}'\n")

        use_vaapi = bool(self.use_vaapi) and bool(self.vaapi_device)
        use_videotoolbox = bool(self.use_videotoolbox)
        audio_args = ['-c:a', 'aac', '-b:a', '192k'] if self.include_audio else ['-an']
        concat_uses_videotoolbox = False

        command = [self.ffmpeg]
        if use_vaapi:
            # VAAPI pipeline for concat: GPU encode only
            command.extend([
                '-f', 'concat',
                '-safe', '0',
                '-i', concat_file,
                '-vaapi_device', self.vaapi_device,
                '-vf', "format=nv12,hwupload,scale_vaapi=640:360",
                '-c:v', 'h264_vaapi',
                '-global_quality', '18',
            ])
        elif nvenc:
            # NVENC (NVIDIA GPU) pipeline
            command.extend([
                '-f', 'concat',
                '-safe', '0',
                '-i', concat_file,
                '-vf', "scale=640:360",
                '-c:v', 'h264_nvenc',
                '-cq:v', '18',
                '-preset', 'p4',
            ])
        elif use_videotoolbox:
            concat_uses_videotoolbox = True
            # VideoToolbox (Apple Silicon/macOS) pipeline
            command.extend([
                '-f', 'concat',
                '-safe', '0',
                '-i', concat_file,
                '-vf', "scale=640:360",
                '-c:v', self.videotoolbox_encoder,
                '-b:v', '2500k',
            ])
        else:
            # Software encoding pipeline
            command.extend([
                '-f', 'concat',
                '-safe', '0',
                '-i', concat_file,
                '-vf', "scale=640:360",
                '-c:v', 'libx264',
                '-crf', '18',
                '-preset', 'slow',
            ])
        command.extend(audio_args)
        command.extend(['-y', '-loglevel', 'quiet', self.output_path])

        try:
            subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=600)
        except subprocess.CalledProcessError as e:
            if concat_uses_videotoolbox:
                print(f"⚠️ VideoToolbox ({self.videotoolbox_encoder}) failed during preview concat for scene {self.scene_id} — {self.scene_name}; falling back to software (libx264).")
                fallback_command = [
                    self.ffmpeg,
                    '-f', 'concat',
                    '-safe', '0',
                    '-i', concat_file,
                    '-vf', "scale=640:360",
                    '-c:v', 'libx264',
                    '-crf', '18',
                    '-preset', 'slow',
                ] + audio_args + ['-y', '-loglevel', 'quiet', self.output_path]
                try:
                    subprocess.run(fallback_command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=600)
                    return
                except subprocess.CalledProcessError as fallback_error:
                    fallback_stderr = fallback_error.stderr.decode('utf-8', errors='replace').strip().splitlines()
                    fallback_detail = fallback_stderr[-1] if fallback_stderr else str(fallback_error)
                    print(f"❌ Software fallback failed for scene {self.scene_id} — {self.scene_name}: {fallback_detail}")
                    raise RuntimeError(f"FFmpeg failed to concatenate clips (software fallback): {fallback_detail}")
            stderr = e.stderr.decode('utf-8', errors='replace').strip().splitlines()
            detail = stderr[-1] if stderr else str(e)
            print(f"❌ Failed to concatenate preview for scene {self.scene_id} — {self.scene_name}: {detail}")
            raise RuntimeError(f"FFmpeg failed to concatenate clips: {detail}")

    def generate_preview(self):
        self.clean_previous_clips()
        start = time.time()
        clips = self.generate_clips()
        if not clips:
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ❌ No clips generated for scene {self.scene_id} — {self.scene_name}")
            return
        try:
            self.concatenate_clips(clips)
            elapsed = time.time() - start
            if os.path.exists(self.output_path):
                if verbose:
                    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ✅ Preview video created for ID {self.scene_id} — {self.scene_name} → {self.output_path} in {elapsed:.2f} seconds.")
            else:
                print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ❌ Preview video not created for ID {self.scene_id} — {self.scene_name}")
        except Exception as e:
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ❌ Preview generation failed for scene {self.scene_id} — {self.scene_name}: {e}")
        finally:
            self.clean_previous_clips()
