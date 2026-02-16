from datetime import datetime, timezone
from uuid import UUID

from shared.events.schemas import UserCreated


def build_user_created_event(user_id: UUID, email: str) -> UserCreated:
    return UserCreated(
        user_id=user_id,
        email=email,
        occurred_at=datetime.now(timezone.utc),
    )


# Publish to SQS/SNS when AWS is configured; for now just build the event
async def publish_user_created(user_id: UUID, email: str) -> None:
    event = build_user_created_event(user_id, email)
    # TODO: send event.model_dump_json() to SQS/SNS
    del event
