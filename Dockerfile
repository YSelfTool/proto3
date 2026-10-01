FROM python:3.11-slim AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libc6-dev libpq-dev \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv

WORKDIR /app
COPY pyproject.toml uv.lock ./

# Change --extra to select other optional dependencies (e.g. froscon, gitlab)
RUN uv sync --frozen --no-dev --no-install-project --extra fsmpi \
    && uv pip install --python .venv/bin/python uwsgi


FROM python:3.11-slim

# The app calls setlocale(LC_TIME, "de_DE.utf8") on import, so the German locale
# must exist. The sed uncomments de_DE.UTF-8 in /etc/locale.gen (all entries are
# commented out by default) and locale-gen then builds it.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 locales cups-bsd \
    texlive-xetex texlive-latex-recommended texlive-latex-extra \
    texlive-fonts-recommended texlive-lang-german fonts-urw-base35 tex-gyre \
    && sed -i 's/^# *de_DE.UTF-8/de_DE.UTF-8/' /etc/locale.gen \
    && locale-gen \
    && rm -rf /var/lib/apt/lists/*

RUN useradd -m -u 1000 appuser \
    && mkdir -p /app /data/documents \
    && chown appuser:appuser /app /data/documents

WORKDIR /app
COPY --from=builder --chown=appuser:appuser /app/.venv /app/.venv
COPY --chown=appuser:appuser . .

ARG GIT_COMMIT_SHA
ARG GIT_COMMIT_TIMESTAMP
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    GIT_COMMIT_SHA=$GIT_COMMIT_SHA \
    GIT_COMMIT_TIMESTAMP=$GIT_COMMIT_TIMESTAMP

USER appuser
EXPOSE 8000

# Mount config.py at /app/config.py and uwsgi.ini at /app/uwsgi.ini.
# DOCUMENTS_PATH in config.py should point to /data/documents.
# uwsgi.ini needs "mule" for the reminder cron (uwsgidecorators).
CMD ["uwsgi", "--ini", "/app/uwsgi.ini"]
