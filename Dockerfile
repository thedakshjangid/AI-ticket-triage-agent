# Official Python image via the AWS public mirror (avoids Docker Hub pull limits)
FROM public.ecr.aws/docker/library/python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY mcp_server ./mcp_server

# Run as a non-root user; give it a writable folder for the default SQLite database.
# docker-compose overrides DATABASE_URL to use PostgreSQL.
RUN useradd --create-home appuser && mkdir -p /app/data && chown appuser /app/data
ENV DATABASE_URL=sqlite:////app/data/triage.db
USER appuser

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
