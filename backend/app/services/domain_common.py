from pydantic import BaseModel
from sqlalchemy import Select, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database.base import Base, utc_now
from app.schemas.football import Page


class DomainError(Exception):
    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


def page_results[T, R: BaseModel](
    session: Session,
    statement: Select[tuple[T]],
    schema: type[R],
    offset: int,
    limit: int,
) -> Page[R]:
    total = (
        session.scalar(
            select(func.count()).select_from(statement.order_by(None).subquery())
        )
        or 0
    )
    rows = session.scalars(statement.offset(offset).limit(limit)).unique().all()
    return Page[R](
        items=[schema.model_validate(row) for row in rows],
        total=total,
        offset=offset,
        limit=limit,
    )


def commit_record[T: Base](session: Session, record: T, conflict: str) -> T:
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise DomainError(409, conflict) from None
    session.refresh(record)
    return record


def apply_changes(record: Base, changes: dict) -> None:
    for name, value in changes.items():
        setattr(record, name, value)
    if "name" in changes:
        record.name_key = changes["name"].casefold()
    record.updated_at = utc_now()
