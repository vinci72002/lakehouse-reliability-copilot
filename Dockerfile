FROM python:3.10-slim-bookworm

RUN apt-get update \
    && apt-get install -y --no-install-recommends openjdk-17-jre-headless \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src
COPY tests ./tests
COPY scripts ./scripts
COPY data/knowledge_base ./data/knowledge_base

RUN pip install --no-cache-dir -e ".[dev]"

CMD ["python", "-m", "pytest"]
