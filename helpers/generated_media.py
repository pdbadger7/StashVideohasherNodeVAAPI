import os
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

        _remove_empty_staging_parents(os.path.dirname(source), staging_base)

    return final_paths


def _remove_empty_staging_parents(path, staging_base):
    path = os.path.normpath(os.path.abspath(path))
    staging_base = os.path.normpath(os.path.abspath(staging_base))

    while os.path.commonpath([path, staging_base]) == staging_base:
        try:
            os.rmdir(path)
        except OSError:
            break

        if path == staging_base:
            break
        path = os.path.dirname(path)
