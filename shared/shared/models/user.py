from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from shared.constants import Role


class CurrentUser(BaseModel):
    """User context from JWT; used by all services."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: UUID
    email: str
    roles: list[Role] = Field(default_factory=list)
