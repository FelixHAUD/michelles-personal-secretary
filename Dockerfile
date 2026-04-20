FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml .
COPY src/ src/
COPY plugins/ plugins/

RUN pip install --no-cache-dir . gunicorn flask

COPY cloud_run.py .

ENV PLUGINS_DIR=/app/plugins

EXPOSE 8080

CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--timeout", "300", "cloud_run:app"]
