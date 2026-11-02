FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app
RUN addgroup --system app && adduser --system --ingroup app app
RUN pip install --no-cache-dir uv
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev
COPY src /app/src
RUN mkdir -p /app/src/staticfiles /app/src/media \
    && chown -R app:app /app
WORKDIR /app/src
USER app
EXPOSE 8000 8001
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
