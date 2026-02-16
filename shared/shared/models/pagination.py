from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class PaginationParams(BaseModel):
    """Query params for list endpoints."""

    model_config = ConfigDict(extra="forbid")

    page: int = Field(ge=1, le=100, description="Page number")
    page_size: int = Field(ge=1, le=100, alias="page_size", description="Items per page")

    def offset(self) -> int:
        return (self.page - 1) * self.page_size

    def limit(self) -> int:
        return self.page_size


class PaginatedResponse(BaseModel, Generic[T]):
    """Wrapped list with total and pagination metadata."""

    model_config = ConfigDict(extra="forbid")

    items: list[T]
    total: int
    page: int
    page_size: int

    @property
    def has_more(self) -> bool:
        return self.page * self.page_size < self.total
