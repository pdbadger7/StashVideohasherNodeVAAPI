FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    XDG_CACHE_HOME=/tmp \
    LIBVA_DRIVERS_PATH=/usr/lib/x86_64-linux-gnu/dri:/usr/lib/aarch64-linux-gnu/dri \
    FFMPEG_BIN=/usr/bin/ffmpeg \
    FFPROBE_BIN=/usr/bin/ffprobe \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1

RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends \
        ca-certificates \
        ffmpeg \
        libva2 \
        libva-drm2 \
        libva-x11-2 \
        mesa-va-drivers \
        tzdata \
        vainfo; \
    arch="$(dpkg --print-architecture)"; \
    if [ "$arch" = "amd64" ]; then \
        apt-get install -y --no-install-recommends i965-va-driver intel-media-va-driver; \
    fi; \
    test -x "$FFMPEG_BIN"; \
    test -x "$FFPROBE_BIN"; \
    "$FFMPEG_BIN" -version >/dev/null; \
    "$FFPROBE_BIN" -version >/dev/null; \
    rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.11.14 /uv /uvx /bin/

WORKDIR /app

# Install dependency graph first to maximize layer cache hits when source changes.
COPY pyproject.toml uv.lock README.md /app/
RUN uv sync --frozen --no-dev --no-install-project

COPY . /app

RUN uv sync --frozen --no-dev

RUN mkdir -p /app/.tmp

ENTRYPOINT ["uv", "run", "stash-videohasher"]
CMD ["--health-check"]
