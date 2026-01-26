"""
HireStack AI Workers
Celery workers for async task processing
"""
from workers.celery_app import app as celery_app

__all__ = ["celery_app"]
