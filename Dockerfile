FROM python:3.13-slim AS build

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app
RUN pip install --no-cache-dir uv
COPY pyproject.toml uv.lock* ./
RUN uv sync --frozen --no-dev || uv sync --no-dev

FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH" \
    DJANGO_SETTINGS_MODULE=project.settings.production

WORKDIR /app
RUN addgroup --system app && adduser --system --ingroup app app
COPY --from=build /app/.venv /app/.venv
COPY src /app/src
COPY docker-entrypoint.sh /app/
RUN chmod +x /app/docker-entrypoint.sh && chown -R app:app /app
USER app
EXPOSE 8000 8001
ENTRYPOINT ["/app/docker-entrypoint.sh"]
CMD ["gunicorn", "project.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--access-logfile", "-", "--error-logfile", "-"]
