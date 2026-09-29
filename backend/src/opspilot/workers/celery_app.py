from celery import Celery

from opspilot.config import get_settings

settings = get_settings()

celery_app = Celery("opspilot", broker=settings.redis_url, backend=settings.redis_url)
celery_app.conf.update(
    task_default_queue="default",
    task_acks_late=True,  # investigations are idempotent; at-least-once delivery is acceptable
    worker_prefetch_multiplier=1,
    timezone="UTC",
    beat_schedule={
        "heartbeat": {"task": "opspilot.workers.tasks.heartbeat", "schedule": 30.0},
    },
)
celery_app.autodiscover_tasks(["opspilot.workers"])
