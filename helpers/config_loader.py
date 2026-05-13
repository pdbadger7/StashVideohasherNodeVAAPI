import os
import platform
from pathlib import Path

import yaml


class ConfigError(RuntimeError):
    pass


def _default_translations(is_windows):
    if is_windows:
        return [
            {"orig": "/data/", "local": "S:/"},
            {"orig": "/xerxes/", "local": "P:/"},
            {"orig": "/data_stranghouse/", "local": "R:/"},
            {"orig": "/mnt/gomorrah/", "local": "G:/"},
        ]
    return [
        {"orig": "/data/", "local": "/mnt/strangyr/"},
        {"orig": "/xerxes/", "local": "/mnt/xerxes/"},
        {"orig": "/data_stranghouse/", "local": "/mnt/stranghouse/"},
        {"orig": "/mnt/gomorrah/", "local": "/mnt/gomorrah/"},
        {"orig": "/data_stranghouse/", "local": "/mnt/Stranghouse/"},
    ]


def get_default_config():
    is_windows = platform.system() == "Windows"
    binary_windows = r".\bin\videohashes-windows.exe"
    binary_linux = r"./bin/videohashes-linux"

    return {
        "windows": is_windows,
        "stash_scheme": "http",
        "stash_host": "192.168.1.71",
        "stash_port": 9999,
        "stash_api_key": None,
        "phash_backend": "binary",
        "binary_windows": binary_windows,
        "binary_linux": binary_linux,
        "binary": binary_windows if is_windows else binary_linux,
        "ffmpeg": os.getenv("FFMPEG_BIN", r"c:\mediatools\ffmpeg.exe" if is_windows else "/usr/bin/ffmpeg"),
        "ffprobe": os.getenv("FFPROBE_BIN", r"c:\mediatools\ffprobe.exe" if is_windows else "/usr/bin/ffprobe"),
        "sprite_path": r"Y:/stash/generated/vtt" if is_windows else "/mnt/stash/stash/generated/vtt",
        "preview_path": r"Y:/stash/generated/screenshots" if is_windows else "/mnt/stash/stash/generated/screenshots",
        "marker_path": r"Y:/stash/generated" if is_windows else "/mnt/stash/stash/generated",
        "excluded_paths": [],
        "hashing_tag": 15015,
        "hashing_error_tag": 15018,
        "cover_error_tag": 15019,
        "translations": _default_translations(is_windows),
        "error_log_path": "error_log.txt",
        "error_log_max_mb": 10,
        "per_page": 25,
        "max_workers": 4,
        "batch_sleep": 5,
        "dry_run": False,
        "once": False,
        "verbose": False,
        "debug": False,
        "filemask": None,
        "vaapi": True,
        "nvenc": False,
        "videotoolbox": False,
        "videotoolbox_codec": "h264",
        "hw_priority": "vaapi",
        "vaapi_override": None,
        "generate_sprite": True,
        "generate_preview": True,
        "preview_audio": False,
        "preview_clips": 15,
        "preview_clip_length": 1,
        "preview_skip_seconds": 15,
        "generate_markers": True,
        "marker_batch_size": 50,
        "marker_preview_enabled": True,
        "marker_thumbnail_enabled": True,
        "marker_screenshot_enabled": True,
        "marker_preview_duration": 20,
        "marker_thumbnail_duration": 5,
        "marker_thumbnail_fps": 12,
    }


def resolve_config_path(cli_config_path):
    if cli_config_path:
        return Path(cli_config_path).expanduser().resolve()

    xdg_config_home = os.getenv("XDG_CONFIG_HOME")
    if xdg_config_home:
        return Path(xdg_config_home).expanduser() / "stash-videohasher" / "config.yml"
    return Path.home() / ".config" / "stash-videohasher" / "config.yml"


def _parse_bool(name, value):
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ConfigError(f"Invalid boolean for {name}: {value!r}")


def _parse_value(name, value, default_value):
    if default_value is None:
        return value
    if isinstance(default_value, bool):
        return _parse_bool(name, value)
    if isinstance(default_value, int):
        try:
            return int(value)
        except ValueError as exc:
            raise ConfigError(f"Invalid integer for {name}: {value!r}") from exc
    if isinstance(default_value, float):
        try:
            return float(value)
        except ValueError as exc:
            raise ConfigError(f"Invalid number for {name}: {value!r}") from exc
    if isinstance(default_value, list):
        text = str(value).strip()
        if not text:
            return []
        if text.startswith("["):
            try:
                parsed = yaml.safe_load(text)
            except yaml.YAMLError as exc:
                raise ConfigError(f"Invalid list for {name}: {value!r}") from exc
            if not isinstance(parsed, list):
                raise ConfigError(f"Invalid list for {name}: {value!r}")
            return parsed
        return [item.strip() for item in text.split(",") if item.strip()]
    return str(value)


def _load_yaml_config(path, defaults):
    if not path.exists():
        raise ConfigError(f"Config file not found: {path}")
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ConfigError(f"Invalid YAML in config file {path}: {exc}") from exc

    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ConfigError(f"Config file must contain a top-level mapping: {path}")

    unknown = sorted(set(data) - set(defaults))
    if unknown:
        names = ", ".join(unknown)
        raise ConfigError(f"Unknown config key(s) in {path}: {names}")
    return data


def _load_env_overrides(defaults):
    overrides = {}
    for key, default_value in defaults.items():
        env_name = f"STASH_VH_{key.upper()}"
        if env_name not in os.environ:
            continue
        overrides[key] = _parse_value(env_name, os.environ[env_name], default_value)
    return overrides


def load_runtime_config(config_path):
    defaults = get_default_config()
    resolved_path = resolve_config_path(config_path)
    yaml_values = _load_yaml_config(resolved_path, defaults)
    env_overrides = _load_env_overrides(defaults)

    merged = dict(defaults)
    merged.update(yaml_values)
    merged.update(env_overrides)

    codec = str(merged.get("videotoolbox_codec", "h264")).lower()
    if codec == "h265":
        codec = "hevc"
    if codec not in {"h264", "hevc"}:
        raise ConfigError(f"Invalid videotoolbox_codec: {merged.get('videotoolbox_codec')!r}")
    merged["videotoolbox_codec"] = codec

    merged["config_path"] = str(resolved_path)
    return merged
