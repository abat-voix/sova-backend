FROM python:3.13-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    POETRY_VERSION=1.8.3 \
    POETRY_VIRTUALENVS_IN_PROJECT=true \
    POETRY_NO_INTERACTION=1

WORKDIR /app

RUN python -m pip install --upgrade pip \
    && python -m pip install "poetry==$POETRY_VERSION"

COPY pyproject.toml poetry.lock ./
RUN poetry install --only main --no-root --no-ansi

FROM python:3.13-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

RUN groupadd --system --gid 10001 sova \
    && useradd --system --uid 10001 --gid sova --home-dir /app --shell /usr/sbin/nologin sova

COPY --from=builder /app/.venv /app/.venv
COPY --chown=sova:sova . .

RUN mkdir -p /app/staticfiles /app/media \
    && chown -R sova:sova /app/staticfiles /app/media

USER sova

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=5 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health/', timeout=3)"]

CMD ["gunicorn", "sova.wsgi:application", "--config", "gunicorn.conf.py"]
