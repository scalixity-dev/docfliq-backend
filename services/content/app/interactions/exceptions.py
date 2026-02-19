# Domain exceptions raised by the interactions service layer.
# The controller layer catches these and converts them to HTTPException.


class AlreadyLikedError(Exception):
    pass


class NotLikedError(Exception):
    pass


class CommentNotFoundError(Exception):
    def __init__(self, comment_id) -> None:
        self.comment_id = comment_id
        super().__init__(f"Comment {comment_id} not found")


class CommentAccessDeniedError(Exception):
    pass


class CommentDepthExceededError(Exception):
    """Raised when trying to reply to a reply (max depth is 2)."""
    pass


class CommentRateLimitError(Exception):
    """Raised when a user exceeds 5 comments per minute."""
    pass


class AlreadyBookmarkedError(Exception):
    pass


class NotBookmarkedError(Exception):
    pass


class PostNotFoundError(Exception):
    def __init__(self, post_id) -> None:
        self.post_id = post_id
        super().__init__(f"Post {post_id} not found")


class AlreadyReportedError(Exception):
    pass


class SelfReportError(Exception):
    """Raised when a user tries to report themselves."""
    pass
