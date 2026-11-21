FROM python:3.14.10-slim

COPY --from=ghcr.io/astral-sh/uv:0.13.1 /uv /bin/uv

# ip reads the neighbor table, ping fills it
RUN apt-get update \
  && apt-get install -y --no-install-recommends iproute2 iputils-ping \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /usr/src/app

COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
  UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy \
  uv sync --locked --no-dev
ENV PATH="/usr/src/app/.venv/bin:$PATH"

COPY . .

# Runs as root: ping needs raw sockets
CMD ["/usr/src/app/main.py"]
