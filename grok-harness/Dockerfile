# Grok-Harness Docker image for container deployment
FROM python:3.11-slim

# Install system dependencies (Playwright will install browser deps)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Create app directory
WORKDIR /app

# Copy project metadata and source
COPY pyproject.toml setup.py ./
COPY src/ ./src/

# Install the package and dependencies (includes playwright)
RUN pip install --no-cache-dir -e .

# Install Playwright Chromium (use shared path for non-root access)
ENV PLAYWRIGHT_BROWSERS_PATH=/app/.playwright
RUN playwright install-deps chromium && playwright install chromium

# Create non-root user for security
RUN useradd -m -u 1000 grok \
    && chown -R grok:grok /app
USER grok

ENV PLAYWRIGHT_BROWSERS_PATH=/app/.playwright

# Persistence for config and data
ENV HOME=/home/grok
VOLUME ["/home/grok/.grok-harness"]

ENTRYPOINT ["grok-harness"]
CMD ["--help"]
