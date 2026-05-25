import os
from pathlib import Path
import shutil

import config


STASH_GENERATED_ROOT = "/root/.stash/generated"


def translate_stash_path(stash_path):
    """Translate a Stash-side path to a local path using config.translations."""
    for translation in getattr(config, "translations", []):
        orig = translation.get("orig")
        local = translation.get("local")
        if not isinstance(orig, str) or not isinstance(local, str):
            continue
        if stash_path.startswith(orig):
            return stash_path.replace(orig, local, 1)
    return stash_path


def generated_media_path(staging_base, stash_subdir, filename):
    """
    Return where a generated media file should be checked or stored locally.

    staging_base is the configured generation directory. When translations can
    map Stash's generated storage to a local mount, the translated destination is
    preferred; otherwise the configured directory remains the final location.
    """
    stash_path = os.path.join(STASH_GENERATED_ROOT, stash_subdir, filename)
    translated = translate_stash_path(stash_path)
    if translated != stash_path:
        return os.path.normpath(translated)
    return os.path.normpath(os.path.join(staging_base, filename))


def prepare_generated_staging_dirs(verbose=False):
    """Create configured generated-media staging directories at startup."""
    for path in _configured_staging_paths():
        os.makedirs(path, exist_ok=True)
        if verbose:
            print(f"📁 Prepared generated-media staging directory: {path}")


def cleanup_generated_staging_dirs(verbose=False):
    """Remove temporary generated-media staging directories at process exit."""
    for path in sorted(_temporary_staging_paths(), key=len, reverse=True):
        if not _safe_to_remove(path):
            if verbose:
                print(f"⚠️ Skipping unsafe generated-media cleanup path: {path}")
            continue
        if not os.path.exists(path):
            continue
        shutil.rmtree(path)
        if verbose:
            print(f"🧹 Cleaned generated-media staging directory: {path}")


def transfer_generated_files(file_paths, staging_base, stash_subdir, verbose=False):
    """
    Move generated files from the configured staging area into translated Stash
    generated storage. Returns the final paths.
    """
    final_paths = []
    staging_base = os.path.normpath(os.path.abspath(staging_base))

    for source in file_paths:
        source = os.path.normpath(os.path.abspath(source))
        rel_name = os.path.relpath(source, staging_base)
        if rel_name.startswith(".."):
            rel_name = os.path.basename(source)

        destination = os.path.abspath(generated_media_path(staging_base, stash_subdir, rel_name))
        if os.path.normcase(source) == os.path.normcase(destination):
            final_paths.append(source)
            continue

        os.makedirs(os.path.dirname(destination), exist_ok=True)
        if os.path.exists(destination):
            os.remove(destination)
        shutil.move(source, destination)
        final_paths.append(destination)

        if verbose:
            print(f"📦 Moved generated media to Stash storage: {destination}")

    return final_paths


def _configured_staging_paths():
    paths = []
    for path in (config.sprite_path, config.preview_path, config.marker_path):
        if not isinstance(path, str) or not path.strip():
            continue
        normalized = os.path.normpath(os.path.abspath(path))
        if normalized not in paths:
            paths.append(normalized)
    return paths


def _temporary_staging_paths():
    paths = []
    mapping = (
        (config.sprite_path, "vtt"),
        (config.preview_path, "screenshots"),
        (config.marker_path, ""),
    )
    for staging_base, stash_subdir in mapping:
        if not isinstance(staging_base, str) or not staging_base.strip():
            continue
        staging_base = os.path.normpath(os.path.abspath(staging_base))
        final_probe = os.path.normpath(os.path.abspath(generated_media_path(staging_base, stash_subdir, ".probe")))
        staging_probe = os.path.normpath(os.path.abspath(os.path.join(staging_base, ".probe")))
        if os.path.normcase(final_probe) != os.path.normcase(staging_probe) and staging_base not in paths:
            paths.append(staging_base)
    return paths


def _safe_to_remove(path):
    path_obj = Path(path).expanduser().resolve()
    if str(path_obj) == path_obj.anchor:
        return False
    if path_obj == Path.home().resolve():
        return False
    return len(path_obj.parts) >= 4
