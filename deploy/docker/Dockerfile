# Source tag resolved 2026-06-23 from Docker Hub registry API:
# python:3.12-slim -> sha256:d764629ce0ddd8c71fd371e9901efb324a95789d2315a47db7e4d27e78f1b0e9
FROM python:3.12-slim@sha256:d764629ce0ddd8c71fd371e9901efb324a95789d2315a47db7e4d27e78f1b0e9 AS build

WORKDIR /app

COPY .github/uv-version.txt /tmp/actionlineage-uv-version.txt
RUN python -m pip install --no-cache-dir "uv==$(cat /tmp/actionlineage-uv-version.txt)"

COPY . /app
RUN uv sync \
    --locked \
    --no-dev \
    --extra service \
    --no-install-project \
    --python /usr/local/bin/python \
    --no-managed-python \
    --no-python-downloads
RUN uv build \
    --out-dir /tmp/actionlineage-dist \
    --python /usr/local/bin/python \
    --no-managed-python \
    --no-python-downloads
RUN uv pip install \
    --python /app/.venv/bin/python \
    --no-deps \
    --reinstall \
    /tmp/actionlineage-dist/*.whl \
    && rm -rf /tmp/actionlineage-dist

FROM python:3.12-slim@sha256:d764629ce0ddd8c71fd371e9901efb324a95789d2315a47db7e4d27e78f1b0e9 AS runtime

WORKDIR /app
COPY --from=build /app/.venv /app/.venv
COPY --from=build /app/contracts /app/contracts

ENV PATH="/app/.venv/bin:${PATH}"
ENTRYPOINT ["actionlineage"]
