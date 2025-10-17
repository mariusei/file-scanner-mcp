# Use a Python image with uv pre-installed (Debian-based for better wheel support)
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

# Install the project into `/app`
WORKDIR /app

# Copy project files
COPY pyproject.toml uv.lock README.md LICENSE ./
COPY src/ ./src/

# Install the project and its dependencies
RUN uv sync --locked --no-dev

# Place executables in the environment at the front of the path
ENV PATH="/app/.venv/bin:$PATH"

# Reset the entrypoint, don't invoke `uv`
ENTRYPOINT []

# Run the HTTP server (Smithery will set PORT=8081)
CMD ["scantool-http"]
