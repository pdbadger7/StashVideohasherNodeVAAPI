import platform
import subprocess


def normalize_videotoolbox_codec(codec):
    """Normalize user-facing VideoToolbox codec aliases."""
    normalized = str(codec or 'h264').strip().lower()
    if normalized == 'h265':
        return 'hevc'
    if normalized not in ('h264', 'hevc'):
        raise ValueError(f"Unsupported VideoToolbox codec '{codec}'. Use 'h264' or 'hevc' (alias: 'h265').")
    return normalized


def get_videotoolbox_encoder(codec='h264'):
    """Return ffmpeg VideoToolbox encoder name for a codec alias."""
    return f"{normalize_videotoolbox_codec(codec)}_videotoolbox"


def is_videotoolbox_available(ffmpeg_path='ffmpeg', codec='h264'):
    """Check whether requested VideoToolbox encoding is available on this host."""
    if platform.system() != "Darwin":
        return False

    try:
        encoder_name = get_videotoolbox_encoder(codec)
        encoders = subprocess.run(
            [ffmpeg_path, '-hide_banner', '-encoders'],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=10
        )
        if encoders.returncode != 0:
            return False

        encoder_output = (encoders.stdout + encoders.stderr).decode('utf-8', errors='replace').lower()
        if encoder_name not in encoder_output:
            return False

        # Optional signal only — do not fail detection if this probe errors.
        subprocess.run(
            [ffmpeg_path, '-hide_banner', '-hwaccels'],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=10
        )
        return True
    except Exception:
        return False
