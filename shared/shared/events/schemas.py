from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class UserCreated(BaseModel):
    """SQS/SNS event: user registered."""

    model_config = ConfigDict(extra="forbid")

    event_type: str = "user.created"
    user_id: UUID
    email: str
    occurred_at: datetime = Field(default_factory=datetime.utcnow)


class OrderCompleted(BaseModel):
    """SQS/SNS event: payment order completed."""

    model_config = ConfigDict(extra="forbid")

    event_type: str = "order.completed"
    order_id: str
    user_id: UUID
    amount_minor: int
    currency: str = "INR"
    occurred_at: datetime = Field(default_factory=datetime.utcnow)
