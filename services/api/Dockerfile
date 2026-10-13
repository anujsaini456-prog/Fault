# syntax=docker/dockerfile:1
FROM python:3.12-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONPATH=/srv
WORKDIR /srv
COPY pyproject.toml ./
# Dependencies only (cached layer); the code is copied in below and run from /srv.
RUN python -c "import tomllib; d = tomllib.load(open('pyproject.toml','rb'))['project']; print('\n'.join(d['dependencies']))" > /tmp/req.txt \
 && pip install -r /tmp/req.txt
RUN useradd --system --uid 10001 --home /srv faultsigma

FROM base AS runtime
COPY --chown=faultsigma alembic.ini ./
COPY --chown=faultsigma alembic ./alembic
COPY --chown=faultsigma app ./app
USER faultsigma
EXPOSE 8000
# The API holds only the RLS-restricted app credentials. Migrations + seed run in the
# separate one-shot "migrate" service (same image, different command and credentials).
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*", "--workers", "2"]

FROM runtime AS test
USER root
RUN python -c "import tomllib; d = tomllib.load(open('pyproject.toml','rb'))['project']; print('\n'.join(d['optional-dependencies']['dev']))" > /tmp/req-dev.txt \
 && pip install -r /tmp/req-dev.txt
COPY --chown=faultsigma tests ./tests
USER faultsigma
ENV COVERAGE_FILE=/tmp/.coverage
CMD ["pytest", "-q", "-p", "no:cacheprovider", "--cov=app", "--cov-report=term-missing"]
