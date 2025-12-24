FROM mcr.microsoft.com/devcontainers/python:3.12-bookworm

# uv: fast, deterministic dependency management
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

RUN apt-get update \
  && apt-get install -y --no-install-recommends \
  ffmpeg \
  graphviz \
  git \
  make \
  curl \
  ca-certificates \
  && apt-get clean \
  && rm -rf /var/lib/apt/lists/*

# Install Piper (pinned release, arch-aware, fails fast if download is not a tar.gz)
ARG PIPER_VERSION="2023.11.14-2"
RUN set -eux; \
  arch="$(uname -m)"; \
  case "${arch}" in \
  x86_64)  piper_arch="x86_64" ;; \
  aarch64|arm64) piper_arch="aarch64" ;; \
  armv7l)  piper_arch="armv7l" ;; \
  *) echo "Unsupported architecture: ${arch}" >&2; exit 1 ;; \
  esac; \
  mkdir -p /opt/piper; \
  url="https://github.com/rhasspy/piper/releases/download/${PIPER_VERSION}/piper_linux_${piper_arch}.tar.gz"; \
  curl -fsSL --retry 5 --retry-delay 2 -o /tmp/piper.tar.gz "${url}"; \
  tar -tzf /tmp/piper.tar.gz >/dev/null; \
  tar -xzf /tmp/piper.tar.gz -C /opt/piper --strip-components=1; \
  ln -sf /opt/piper/piper /usr/local/bin/piper; \
  rm -f /tmp/piper.tar.gz; \
  piper --help >/dev/null
