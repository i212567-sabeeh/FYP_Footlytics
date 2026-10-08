"""Start the separate RQ worker with the same settings and serializer as the API."""

import argparse
import logging
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from redis.exceptions import RedisError  # noqa: E402
from rq import Worker  # noqa: E402
from rq.serializers import JSONSerializer  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.workers.queue import redis_connection, rq_queue  # noqa: E402
from app.workers.video_preparation import record_workhorse_failure  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the FOOTLYTICS video-processing worker"
    )
    parser.add_argument(
        "--burst", action="store_true", help="Exit after the current queue is empty"
    )
    args = parser.parse_args()
    if os.name == "nt":
        print(
            "Run this RQ worker in Linux/WSL with a Linux Python environment. "
            "The installed RQ worker uses POSIX process APIs."
        )
        return 1
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    settings = get_settings()
    connection = redis_connection(settings)
    try:
        connection.ping()
        worker = Worker(
            [rq_queue(settings, connection)],
            connection=connection,
            serializer=JSONSerializer,
            log_job_description=False,
            work_horse_killed_handler=record_workhorse_failure,
        )
        worker.work(burst=args.burst)
    except RedisError:
        print(
            "Redis is unavailable. Start Redis and check REDIS_URL "
            "before restarting the worker."
        )
        return 1
    finally:
        connection.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
