"""
Celery Application Configuration
For handling async tasks like document generation, exports, etc.
"""
import os
from celery import Celery

# Redis URL from environment
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")

# Create Celery app
app = Celery(
    "hirestack",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=["workers.tasks.document_tasks", "workers.tasks.export_tasks"],
)

# Celery configuration
app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=600,  # 10 minutes max per task
    worker_prefetch_multiplier=1,
    worker_concurrency=4,
    result_expires=3600,  # Results expire after 1 hour
)

# Task routes for different queues
app.conf.task_routes = {
    "workers.tasks.document_tasks.*": {"queue": "documents"},
    "workers.tasks.export_tasks.*": {"queue": "exports"},
}

if __name__ == "__main__":
    app.start()
