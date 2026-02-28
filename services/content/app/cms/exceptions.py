# Domain exceptions raised by the service layer.
# The controller layer catches these and converts them to HTTPException.


class PostNotFoundError(Exception):
    def __init__(self, post_id) -> None:
        self.post_id = post_id
        super().__init__(f"Post {post_id} not found")


class PostAccessDeniedError(Exception):
    pass


class PostNotPublishableError(Exception):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


class ChannelNotFoundError(Exception):
    def __init__(self, channel_id) -> None:
        self.channel_id = channel_id
        super().__init__(f"Channel {channel_id} not found")


class ChannelSlugTakenError(Exception):
    def __init__(self, slug: str) -> None:
        self.slug = slug
        super().__init__(f"Channel slug '{slug}' is already taken")


class ChannelAccessDeniedError(Exception):
    pass


class PostNotRestorableError(Exception):
    def __init__(self, version_number: int) -> None:
        self.version_number = version_number
        super().__init__(f"Version {version_number} not found for this post")


class DuplicateContentError(Exception):
    """Raised when a post with identical content was submitted within the last 60 seconds."""

    pass
