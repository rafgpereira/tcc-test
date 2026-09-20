# Single image for the whole project (Constitution, Principles II and V).
# Base: exact GCC 13.2.0 (Debian 12), pinned by digest for reproducibility.
# uv image digest (index) resolved on 2026-09-20: sha256:10787c682e4184e4f290de1171fd4703dc63de99221f10fe1c99002ce7fa9acc
FROM gcc:13.2.0@sha256:15c73bc59ae88b3fd563ef2ec4a8743a8848a9f74362b6d116c4543c4844b6e0

ENV LANG=C.UTF-8 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_INSTALL_DIR=/opt/python \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH=/opt/venv/bin:$PATH \
    PYTHONPATH=/app/src

# uv is only used at build time; there is no dependency resolution or network at run time.
COPY --from=ghcr.io/astral-sh/uv:0.12.17@sha256:10787c682e4184e4f290de1171fd4703dc63de99221f10fe1c99002ce7fa9acc /uv /usr/local/bin/uv

WORKDIR /app

# CPython 3.11.16 (from .python-version) and the locked dependencies, including the dev group.
COPY .python-version pyproject.toml uv.lock ./
RUN uv sync --frozen

RUN useradd --uid 1000 --create-home pipeline

# Code and tests are copied so the image works without mounts; docker-compose.override.yml
# mounts the working tree for development. No secrets: .env is excluded by .dockerignore.
COPY src ./src
COPY scripts ./scripts
COPY tests ./tests
# The .gitignore rule test runs inside the container.
COPY .gitignore ./.gitignore
