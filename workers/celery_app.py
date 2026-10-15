"""
creditsense/workers/celery_app.py
---------------------------------
Celery Application instance configuration for distributed background underwriting tasks.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from celery import Celery

# Add package root to sys.path
ROOT = Path(__file__).parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

REDIS_BROKER_URL = os.environ.get(
    "CELERY_BROKER_URL",
    os.environ.get("REDIS_URL", "redis://localhost:6379/0"),
)

REDIS_RESULT_BACKEND = os.environ.get(
    "CELERY_RESULT_BACKEND",
    "redis://localhost:6379/1",
)

celery_app = Celery(
    "creditsense_worker",
    broker=REDIS_BROKER_URL,
    backend=REDIS_RESULT_BACKEND,
    include=["workers.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    # Worker optimization for ML/AI compute tasks
    worker_prefetch_multiplier=1,  # Fair task distribution, prevents worker starvation
    task_acks_late=True,           # Ensure task is only acknowledged after full completion
    task_reject_on_worker_lost=True, # Re-enqueue if worker container crashes
    task_soft_time_limit=45,       # 45 seconds soft timeout (raises SoftTimeLimitExceeded)
    task_time_limit=60,            # 60 seconds hard SIGKILL timeout
    task_default_queue="underwriting_queue",
    task_routes={
        "workers.tasks.process_underwriting_application": {"queue": "underwriting_queue"},
    },
)


if __name__ == "__main__":
    celery_app.start()
