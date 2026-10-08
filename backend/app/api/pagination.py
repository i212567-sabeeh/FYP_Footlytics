from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Query


@dataclass
class Pagination:
    offset: Annotated[int, Query(ge=0, le=2**31 - 1)] = 0
    limit: Annotated[int, Query(ge=1, le=100)] = 25


PaginationQuery = Annotated[Pagination, Depends()]
