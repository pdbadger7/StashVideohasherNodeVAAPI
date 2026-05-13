# Copilot instructions for StashVideohasherNodeVAAPI

## Build, test, and lint commands

This repository does not define a formal build step, lint tool, or automated unit test suite.

Use these project-native validation commands instead:

```bash
# Install dependencies
pip install -r requirements.txt

# Main readiness check (connectivity, ffmpeg, backend, writable paths, GPU encode test when applicable)
python phash_videohasher_main.py --health-check

# Targeted single-batch run against a narrow subset (closest equivalent to a "single test")
python phash_videohasher_main.py --once --batch-size 1 --filemask "YourPattern*" --dry-run --verbose
```

For targeted generator validation on one input file:

```bash
python benchmarking/sprite_benchmark.py --input /path/video.mkv --output /tmp/sprite.jpg
python benchmarking/preview_benchmark.py --input /path/video.mkv --output /tmp/preview.mp4
```

## High-level architecture

The system is a threaded Stash worker that can run on multiple nodes and process video jobs safely in parallel.

1. `phash_videohasher_main.py` is the orchestrator: parses CLI flags, mutates `config` at runtime, detects hardware encoder once, runs health checks, then dispatches work through a `ThreadPoolExecutor`.
2. Work runs in two modes:
   - **Integrated scene mode** (default): discovers scenes missing phash, then per scene performs phash + cover + optional sprite/preview/marker generation.
   - **Standalone media mode** (`--standalone-*`): discovers missing sprites/previews/markers independently of phash status and backfills only that media.
3. Stash coordination is tag-driven via `helpers/stash_utils.py`:
   - claim with `hashing_tag`
   - tag failures with `hashing_error_tag` / `cover_error_tag`
   - always release claim in `finally`
4. Scene selection is intentionally randomized by page (`helpers/scene_discovery.py`) to reduce cross-node collisions, with tag-claiming providing race mitigation.
5. Hardware path is decided once at startup (VAAPI/NVENC/software) and passed through workers/generators; generator code should not re-detect VAAPI per frame/clip.

## Key repository conventions

1. **`config.py` is runtime state, loaded from YAML.** CLI flags override config values in `apply_cli_args()`, and helpers read from the shared module.
2. **Always preserve claim/release safety.** Any scene-processing change must keep release in `finally` semantics so stuck `hashing_tag` states are avoided.
3. **Respect dry-run behavior in Stash write paths.** Mutating operations in `stash_utils` should gate on `dry_run` and print intended actions.
4. **Translate paths before filesystem access.** Scene file paths from Stash must pass through `translations` mapping before existence checks and processing.
5. **Treat per-scene failures as isolated.** Existing behavior logs and tags failures while continuing the batch; avoid introducing fail-fast behavior for the whole batch.
6. **Temporary artifacts belong under `.tmp/` and are cleaned frequently.** New processing steps should follow the same temp-dir lifecycle.
