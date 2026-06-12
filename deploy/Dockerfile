# syntax=docker/dockerfile:1

# ---- base ----
FROM python:3.12-slim AS base
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

# tesseract is required by the local parse fallback (pytesseract).
RUN apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr libpq5 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# ---- deps (cached layer) ----
FROM base AS deps
COPY pyproject.toml README.md ./
COPY app ./app
RUN pip install --upgrade pip && pip install .

# ---- runtime ----
FROM base AS runtime
# Bring in installed site-packages + console scripts from the deps stage.
COPY --from=deps /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=deps /usr/local/bin /usr/local/bin

COPY app ./app
COPY migrations ./migrations

# Run as non-root.
RUN useradd --create-home --uid 10001 appuser \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=5 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/health').status==200 else 1)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

# ---- test ----
# Full dependency set + dev tools (ruff/mypy/pytest) + test sources. Used by the
# `test` compose service to run lint, type-check, and the unit+integration suite
# against a real Postgres. Not part of the runtime image.
#
# Dependencies are installed against a stub package BEFORE the real source is
# copied, so editing app/tests invalidates only the cheap COPY layers -- not the
# slow dependency install. Editable install means the later COPY of real source
# is picked up at runtime without reinstalling.
FROM base AS test
COPY pyproject.toml README.md ./
RUN mkdir -p app && touch app/__init__.py \
    && pip install --upgrade pip && pip install -e ".[dev]"
COPY app ./app
COPY migrations ./migrations
COPY tests ./tests
CMD ["pytest", "-ra"]
