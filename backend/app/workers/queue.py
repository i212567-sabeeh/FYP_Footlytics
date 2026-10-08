"""One queue boundary, injectable in tests; API requests never execute work."""

from typing import Annotated, Protocol

from fastapi import Depends, Request
from redis import Redis
from redis.exceptions import RedisError
from rq import Queue
from rq.job import Callback
from rq.serializers import JSONSerializer

from app.core.config import Settings


class QueueUnavailable(Exception):
    pass


class JobQueue(Protocol):
    def enqueue_match_report(
        self, job_id: int, attempt: int, rq_job_id: str
    ) -> None: ...

    def enqueue_team_tactical_analytics(
        self, job_id: int, attempt: int, rq_job_id: str
    ) -> None: ...

    def enqueue_video_preparation(
        self, job_id: int, attempt: int, rq_job_id: str
    ) -> None: ...

    def enqueue_player_detection(
        self, job_id: int, attempt: int, rq_job_id: str
    ) -> None: ...

    def enqueue_player_tracking(
        self, job_id: int, attempt: int, rq_job_id: str
    ) -> None: ...

    def enqueue_team_classification(
        self, job_id: int, attempt: int, rq_job_id: str
    ) -> None: ...

    def enqueue_coordinate_mapping(
        self, job_id: int, attempt: int, rq_job_id: str
    ) -> None: ...

    def enqueue_trajectory_cleaning(
        self, job_id: int, attempt: int, rq_job_id: str
    ) -> None: ...

    def enqueue_player_analytics(
        self, job_id: int, attempt: int, rq_job_id: str
    ) -> None: ...


def redis_connection(settings: Settings) -> Redis:
    return Redis.from_url(
        settings.redis_url,
        socket_connect_timeout=settings.redis_connect_timeout_seconds,
        socket_timeout=settings.redis_connect_timeout_seconds,
        retry_on_timeout=False,
    )


def rq_queue(settings: Settings, connection: Redis) -> Queue:
    return Queue(
        settings.rq_queue_name,
        connection=connection,
        serializer=JSONSerializer,
        default_timeout=settings.rq_job_timeout_seconds,
    )


class RQJobQueue:
    def enqueue_match_report(self, job_id: int, attempt: int, rq_job_id: str) -> None:
        self._enqueue(
            "app.workers.match_report.generate_report",
            job_id,
            attempt,
            rq_job_id,
            self.settings.rq_job_timeout_seconds,
        )

    def enqueue_team_tactical_analytics(
        self, job_id: int, attempt: int, rq_job_id: str
    ) -> None:
        self._enqueue(
            "app.workers.team_analytics.analyze_teams",
            job_id,
            attempt,
            rq_job_id,
            self.settings.detection_job_timeout_seconds,
        )

    def __init__(self, settings: Settings):
        self.settings = settings
        self.connection = redis_connection(settings)
        self.queue = rq_queue(settings, self.connection)

    def close(self) -> None:
        self.connection.close()

    def enqueue_video_preparation(
        self, job_id: int, attempt: int, rq_job_id: str
    ) -> None:
        self._enqueue(
            "app.workers.video_preparation.prepare_video",
            job_id,
            attempt,
            rq_job_id,
            self.settings.rq_job_timeout_seconds,
        )

    def enqueue_player_detection(
        self, job_id: int, attempt: int, rq_job_id: str
    ) -> None:
        self._enqueue(
            "app.workers.player_detection.detect_players",
            job_id,
            attempt,
            rq_job_id,
            self.settings.detection_job_timeout_seconds,
        )

    def enqueue_player_tracking(
        self, job_id: int, attempt: int, rq_job_id: str
    ) -> None:
        self._enqueue(
            "app.workers.player_tracking.track_players",
            job_id,
            attempt,
            rq_job_id,
            self.settings.detection_job_timeout_seconds,
        )

    def enqueue_team_classification(
        self, job_id: int, attempt: int, rq_job_id: str
    ) -> None:
        self._enqueue(
            "app.workers.team_classification.classify_teams",
            job_id,
            attempt,
            rq_job_id,
            self.settings.detection_job_timeout_seconds,
        )

    def enqueue_coordinate_mapping(
        self, job_id: int, attempt: int, rq_job_id: str
    ) -> None:
        self._enqueue(
            "app.workers.coordinate_mapping.map_coordinates",
            job_id,
            attempt,
            rq_job_id,
            self.settings.detection_job_timeout_seconds,
        )

    def enqueue_trajectory_cleaning(
        self, job_id: int, attempt: int, rq_job_id: str
    ) -> None:
        self._enqueue(
            "app.workers.trajectory_cleaning.clean_trajectories",
            job_id,
            attempt,
            rq_job_id,
            self.settings.detection_job_timeout_seconds,
        )

    def enqueue_player_analytics(
        self, job_id: int, attempt: int, rq_job_id: str
    ) -> None:
        self._enqueue(
            "app.workers.player_analytics.analyze_players",
            job_id,
            attempt,
            rq_job_id,
            self.settings.detection_job_timeout_seconds,
        )

    def _enqueue(
        self, task: str, job_id: int, attempt: int, rq_job_id: str, timeout: int
    ) -> None:
        try:
            self.queue.enqueue(
                task,
                kwargs={"processing_job_id": job_id, "attempt": attempt},
                job_id=rq_job_id,
                unique=True,
                job_timeout=timeout,
                result_ttl=self.settings.rq_result_ttl_seconds,
                failure_ttl=self.settings.rq_result_ttl_seconds,
                on_failure=Callback("app.workers.video_preparation.record_rq_failure"),
            )
        except RedisError as error:
            raise QueueUnavailable("The processing queue is unavailable") from error


async def get_job_queue(request: Request) -> JobQueue:
    # Constructed once per application; creating a Redis client makes no connection.
    if not hasattr(request.app.state, "job_queue"):
        request.app.state.job_queue = RQJobQueue(request.app.state.settings)
    return request.app.state.job_queue


QueueDependency = Annotated[JobQueue, Depends(get_job_queue)]
