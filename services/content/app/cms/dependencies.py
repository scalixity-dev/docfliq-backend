from uuid import UUID

from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.channel import Channel
from app.models.post import Post
from app.cms import service
from app.cms.exceptions import ChannelNotFoundError, PostNotFoundError


async def get_post_or_404(
    post_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> Post:
    try:
        return await service.get_post_by_id(post_id, db)
    except PostNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Post {post_id} not found",
        )


async def get_channel_or_404(
    channel_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> Channel:
    try:
        return await service.get_channel_by_id(channel_id, db)
    except ChannelNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Channel {channel_id} not found",
        )
