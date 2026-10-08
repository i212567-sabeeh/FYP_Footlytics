from datetime import datetime

from pydantic import Field

from app.schemas.football import ReadModel


class ReportSummary(ReadModel):
    generated_at: datetime
    page_count: int = Field(ge=1)
    size_bytes: int = Field(gt=0)
    player_rows: int = Field(ge=0)
    team_rows: int = Field(ge=0)
    heatmaps: int = Field(ge=0)
    sections: list[str]


class ReportStatus(ReadModel):
    available: bool
    current: bool
    stale: bool
    job_id: int | None = None
    summary: ReportSummary | None = None
