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
        "rollup": {"task": "opspilot.workers.tasks.rollup_service_metrics", "schedule": 15.0},
        "detect": {"task": "opspilot.workers.tasks.detect_incidents", "schedule": 15.0},
        "investigate": {"task": "opspilot.workers.tasks.investigate_pending", "schedule": 15.0},
        "partitions": {"task": "opspilot.workers.tasks.maintain_partitions", "schedule": 3600.0},
    },
)
celery_app.autodiscover_tasks(["opspilot.workers"])
