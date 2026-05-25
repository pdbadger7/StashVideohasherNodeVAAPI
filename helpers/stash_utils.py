# stash_utils.py

from stashapi.stashapp import StashInterface
import config
from datetime import datetime
import os
import threading
from fnmatch import fnmatch

# Initialize Stash connection with optional API key
stash_config = {
    "scheme": config.stash_scheme,
    "host": config.stash_host,
    "port": config.stash_port
}

# Add API key to config if it's set
if config.stash_api_key:
    stash_config["apikey"] = config.stash_api_key

stash = StashInterface(stash_config)

# Thread-safe error logging
error_log_lock = threading.Lock()
failed_scene_lock = threading.Lock()
failed_scene_ids_this_run = set()


def mark_scene_failed_this_run(scene_id):
    with failed_scene_lock:
        failed_scene_ids_this_run.add(str(scene_id))


def is_scene_failed_this_run(scene_id):
    with failed_scene_lock:
        return str(scene_id) in failed_scene_ids_this_run

def progress_safe_print(message):
    """Print in a way that cooperates with active tqdm bars."""
    try:
        from tqdm import tqdm
        tqdm.write(message)
    except Exception:
        print(message)

def _rotate_log_if_needed():
    """Rotate error_log_path if it exceeds error_log_max_mb. Called inside error_log_lock."""
    if config.error_log_max_mb <= 0:
        return
    try:
        if os.path.exists(config.error_log_path) and os.path.getsize(config.error_log_path) > config.error_log_max_mb * 1024 * 1024:
            rotated = config.error_log_path + ".1"
            if os.path.exists(rotated):
                os.remove(rotated)
            os.rename(config.error_log_path, rotated)
    except Exception:
        pass  # Rotation failure is non-fatal

def log_scene_failure(scene_id, filename_pretty, step, error):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    msg = f"{timestamp} ❌ Scene {scene_id} — {filename_pretty} failed during {step}: {error}"
    try:
        progress_safe_print(msg)
    except UnicodeEncodeError:
        progress_safe_print(msg.encode('utf-8', errors='replace').decode('ascii', errors='replace'))

def reset_terminal():
    import platform
    import sys
    if platform.system() != "Windows":
        # Reset all terminal attributes
        print("\033[0m", end="")  # Reset colors/attributes
        print("\033[?25h", end="")  # Show cursor
        sys.stdout.flush()
        # Use stty to reset terminal state (handles echo, input modes, etc.)
        import subprocess
        try:
            subprocess.run(["stty", "sane"], check=False)
        except:
            pass  # If stty fails, at least we reset colors/cursor

def get_total_scene_count(include_hashing_tag=False):
    """
    Count scenes still pending phash generation.

    Args:
        include_hashing_tag (bool): When True, include scenes currently claimed with
            hashing_tag so queue size reflects multi-node in-flight work.
    """
    excluded_tags = [config.hashing_error_tag, config.cover_error_tag]
    if not include_hashing_tag:
        excluded_tags.insert(0, config.hashing_tag)

    query_filter = {
        "phash": {"value": "", "modifier": "IS_NULL"},
        "tags": {"value": excluded_tags, "modifier": "EXCLUDES"}
    }

    needs_path_filter = bool(config.excluded_paths or config.filemask or failed_scene_ids_this_run)
    if needs_path_filter:
        # Need file paths to apply excluded_paths/filemask filters client-side.
        scenes = stash.find_scenes(
            f=query_filter,
            filter={"per_page": -1},
            fragment="id files{path}"
        )
        total = 0
        for scene in scenes:
            if is_scene_failed_this_run(scene.get('id')):
                continue
            files = scene.get('files') or []
            if not files:
                continue

            file_path = files[0].get('path', '')
            if config.excluded_paths and any(file_path.startswith(ep) for ep in config.excluded_paths):
                continue
            if config.filemask and not fnmatch(os.path.basename(file_path), config.filemask):
                continue
            total += 1
        return total

    count, _ = stash.find_scenes(
        f=query_filter,
        filter={"per_page": 1},
        fragment="id",
        get_count=True
    )
    return count

def tag_scene_error(scene_id, error_tag, error_msg=None):
    mark_scene_failed_this_run(scene_id)
    if config.dry_run:
        print(f"[DRY RUN] Would tag scene {scene_id} with error tag {error_tag}")
        return True

    tagged = True
    try:
        stash.update_scenes({"ids": [scene_id], "tag_ids": {"ids": error_tag, "mode": "ADD"}})
        stash.update_scenes({"ids": [scene_id], "tag_ids": {"ids": config.hashing_tag, "mode": "REMOVE"}})
    except Exception as tag_err:
        tagged = False
        print(f"⚠️ Failed to apply error tag {error_tag} to scene {scene_id}; suppressing retry for this run: {tag_err}")

    if error_msg:
        # Thread-safe error logging
        try:
            with error_log_lock:
                _rotate_log_if_needed()
                with open(config.error_log_path, "a", encoding="utf-8") as log:
                    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    log.write(f"[{timestamp}] Scene {scene_id}: {error_msg}\n")
        except Exception as log_err:
            print(f"⚠️ Failed to write {config.error_log_path}: {log_err}")
    return tagged

def claim_scene(scene_id):
    if config.dry_run:
        print(f"[DRY RUN] Would claim scene {scene_id}")
        return
    stash.update_scenes({"ids": [scene_id], "tag_ids": {"ids": config.hashing_tag, "mode": "ADD"}})

def release_scene(scene_id):
    if config.dry_run:
        print(f"[DRY RUN] Would release scene {scene_id}")
        return
    stash.update_scenes({"ids": [scene_id], "tag_ids": {"ids": config.hashing_tag, "mode": "REMOVE"}})

def update_phash(file_id, phash):
    if config.dry_run:
        print(f"[DRY RUN] Would update phash for file {file_id} to {phash}")
        return
    stash.file_set_fingerprints(file_id, [{"type": "phash", "value": phash}])

def update_cover(scene_id, cover_data):
    if config.dry_run:
        print(f"[DRY RUN] Would update cover image for scene {scene_id}")
        return True
    return stash.update_scene({"id": scene_id, "cover_image": cover_data})

def get_error_scenes():
    """Get scenes with error tags for retry"""
    return stash.find_scenes(
        f={"tags": {"value": [config.hashing_error_tag, config.cover_error_tag], "modifier": "INCLUDES"}},
        filter={"sort": "created_at", "direction": "DESC", "per_page": -1},
        fragment="id files{id path fingerprints{value type}} paths{screenshot}"
    )

def clear_error_tags(scene_ids):
    """Clear error tags from scenes"""
    if config.dry_run:
        print(f"[DRY RUN] Would clear error tags from {len(scene_ids)} scenes")
        return
    for scene_id in scene_ids:
        stash.update_scenes({"ids": [scene_id], "tag_ids": {"ids": config.hashing_error_tag, "mode": "REMOVE"}})
        stash.update_scenes({"ids": [scene_id], "tag_ids": {"ids": config.cover_error_tag, "mode": "REMOVE"}})

def get_hashing_scenes():
    """Get scenes currently tagged with the in-process hashing tag"""
    return stash.find_scenes(
        f={"tags": {"value": [config.hashing_tag], "modifier": "INCLUDES"}},
        filter={"per_page": -1},
        fragment="id"
    )

def clear_hashing_tags(scene_ids):
    """Clear the in-process hashing tag from scenes (recover from crashed runs)"""
    if config.dry_run:
        print(f"[DRY RUN] Would clear hashing tag from {len(scene_ids)} scenes")
        return
    for scene_id in scene_ids:
        stash.update_scenes({"ids": [scene_id], "tag_ids": {"ids": config.hashing_tag, "mode": "REMOVE"}})

def get_scene_markers_with_files(scene_id):
    """
    Get markers for a scene with file information.
    Used during integrated mode (scene processing).

    Args:
        scene_id: Stash scene ID

    Returns:
        list: Marker objects with scene file metadata
    """
    return stash.get_scene_markers(
        scene_id,
        fragment="id title seconds scene { id files { path fingerprints { type value } } }"
    )

def log_marker_failure(marker_id, marker_title, step, error):
    """
    Log marker generation failure.
    Similar to log_scene_failure but for markers.

    Args:
        marker_id: Stash marker ID
        marker_title: Marker title for display
        step: Processing step that failed
        error: Error message or exception
    """
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    msg = f"{timestamp} ❌ Marker {marker_id} — {marker_title} failed during {step}: {error}"
    try:
        progress_safe_print(msg)
    except UnicodeEncodeError:
        progress_safe_print(msg.encode('utf-8', errors='replace').decode('ascii', errors='replace'))

    # Thread-safe error logging
    try:
        with error_log_lock:
            _rotate_log_if_needed()
            with open(config.error_log_path, "a", encoding="utf-8") as log:
                log.write(f"[{timestamp}] Marker {marker_id} — {marker_title}: {step} failed: {error}\n")
    except Exception as log_err:
        print(f"⚠️ Failed to write {config.error_log_path}: {log_err}")
