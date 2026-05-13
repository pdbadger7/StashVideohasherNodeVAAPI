import os

import config
from helpers.stash_utils import stash

_FIND_TAGS_QUERY = """
query FindTags($filter: FindFilterType) {
    findTags(filter: $filter) {
        tags { id name }
    }
}
"""

_CREATE_TAG_MUTATION = """
mutation TagCreate($input: TagCreateInput!) {
    tagCreate(input: $input) {
        id
        name
    }
}
"""

_TAG_SPECS = [
    ("hashing_tag", ("In Process",)),
    ("hashing_error_tag", ("Phash Error", "Hashing Error")),
    ("cover_error_tag", ("Cover Error",)),
]


def _is_missing_tag_id(value):
    return not isinstance(value, int) or value <= 0


def _scene_path_prefix(path):
    if not isinstance(path, str) or not path.startswith("/"):
        return None
    parts = path.split("/")
    if len(parts) < 2 or not parts[1]:
        return None
    return f"/{parts[1]}/"


def _local_root_candidates():
    candidates = []
    for output_path in (config.marker_path, config.preview_path, config.sprite_path):
        if not isinstance(output_path, str):
            continue
        generated_root = os.path.dirname(output_path.rstrip(os.sep))
        if generated_root and generated_root not in candidates:
            candidates.append(generated_root)
    return [c if c.endswith(os.sep) else c + os.sep for c in candidates]


def _fetch_all_tags():
    result = stash.call_GQL(_FIND_TAGS_QUERY, {"filter": {"per_page": -1}})
    return result.get("findTags", {}).get("tags", [])


def _create_tag(name):
    result = stash.call_GQL(_CREATE_TAG_MUTATION, {"input": {"name": name}})
    created = result.get("tagCreate")
    if isinstance(created, dict):
        return created
    if isinstance(created, int):
        return {"id": created, "name": name}
    raise RuntimeError(f"Unexpected tagCreate response for '{name}': {created!r}")


def _ensure_missing_tags(verbose=False):
    tags = _fetch_all_tags()
    by_name = {
        str(t.get("name", "")).strip().lower(): t
        for t in tags
        if t.get("name") and t.get("id") is not None
    }
    changed = []

    for attr_name, tag_names in _TAG_SPECS:
        current_value = getattr(config, attr_name, None)
        if not _is_missing_tag_id(current_value):
            continue

        matched_tag = None
        for candidate_name in tag_names:
            matched_tag = by_name.get(candidate_name.lower())
            if matched_tag:
                break

        if not matched_tag:
            if config.dry_run:
                print(f"⚠️ {attr_name} is missing and tag '{tag_names[0]}' does not exist (dry-run: not creating tag).")
                continue
            matched_tag = _create_tag(tag_names[0])
            by_name[tag_names[0].lower()] = matched_tag
            if verbose:
                print(f"🏷️ Created Stash tag '{matched_tag.get('name', tag_names[0])}' (id={matched_tag.get('id')}).")

        tag_id = int(matched_tag["id"])
        setattr(config, attr_name, tag_id)
        changed.append((attr_name, tag_id, matched_tag.get("name", tag_names[0])))
        if verbose:
            print(f"🏷️ Auto-filled {attr_name}={tag_id} ({matched_tag.get('name', tag_names[0])}).")

    return changed


def _derive_translation_from_scenes(verbose=False):
    current_translations = getattr(config, "translations", None)
    if current_translations:
        return None

    scenes = stash.find_scenes(
        f={},
        filter={"per_page": 25},
        fragment="files { path }",
    )
    if not scenes:
        return None

    local_roots = _local_root_candidates()
    if not local_roots:
        return None

    match_counts = {}
    for scene in scenes:
        for file_info in scene.get("files", []):
            stash_path = file_info.get("path")
            if not isinstance(stash_path, str):
                continue
            if os.path.exists(stash_path):
                continue

            prefix = _scene_path_prefix(stash_path)
            if not prefix:
                continue

            for local_root in local_roots:
                translated = stash_path.replace(prefix, local_root, 1)
                if os.path.exists(translated):
                    key = (prefix, local_root)
                    match_counts[key] = match_counts.get(key, 0) + 1

    if not match_counts:
        return None

    (orig_prefix, local_prefix), hits = max(match_counts.items(), key=lambda item: item[1])
    translation = {"orig": orig_prefix, "local": local_prefix}
    config.translations = [translation]
    if verbose:
        print(f"🛣️ Auto-filled translations with {translation} (matched {hits} scene path(s)).")
    return translation


def autofill_missing_setup(verbose=False):
    """
    Auto-fill missing setup values in runtime config:
    - missing tag IDs (fetch existing tags, create if needed)
    - missing path translations (best-effort from scene paths and local mounts)
    """
    try:
        stash.find_scenes(filter={"per_page": 1}, fragment="id")
    except Exception as exc:
        if verbose:
            print(f"⚠️ Skipping setup autofill: cannot reach Stash API ({exc})")
        return

    tag_changes = _ensure_missing_tags(verbose=verbose)
    translation_change = _derive_translation_from_scenes(verbose=verbose)

    if verbose and (tag_changes or translation_change):
        print("✅ Setup autofill applied to in-memory config.")
