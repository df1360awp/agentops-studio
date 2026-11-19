FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 AGENTOPS_DB_PATH=/app/data/studio.sqlite3
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && useradd --system --uid 10001 --create-home appuser
COPY --chown=appuser:appuser app/ app/
COPY --chown=appuser:appuser web/ web/
COPY --chown=appuser:appuser data/example_*.csv data/
RUN mkdir -p /app/data && chown appuser:appuser /app/data
USER appuser
EXPOSE 8765
# Bind locally unless deliberately placed behind a secure reverse proxy with AGENTOPS_API_TOKEN.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8765"]
