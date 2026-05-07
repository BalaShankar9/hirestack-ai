web: cd /app/backend && PYTHONPATH=/app python -m uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}
worker: cd /app/backend && PYTHONPATH=/app python -m app.worker
scheduler: cd /app/backend && PYTHONPATH=/app python -m app.scheduler.main
outbox_relay: cd /app/backend && PYTHONPATH=/app python -m app.workers.outbox_relay
billing_usage_consumer: cd /app/backend && PYTHONPATH=/app python -m app.workers.consumers.billing_usage
