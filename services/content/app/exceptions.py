"""Shared HTTP exception classes reused across all content service domains."""

from fastapi import HTTPException, status


class NotFoundError(HTTPException):
    def __init__(self, resource: str = "Resource") -> None:
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"{resource} not found.",
        )


class ForbiddenError(HTTPException):
    def __init__(self, detail: str = "You do not have permission to perform this action.") -> None:
        super().__init__(status_code=status.HTTP_403_FORBIDDEN, detail=detail)


class ConflictError(HTTPException):
    def __init__(self, detail: str = "Resource already exists.") -> None:
        super().__init__(status_code=status.HTTP_409_CONFLICT, detail=detail)


class UnprocessableError(HTTPException):
    def __init__(self, detail: str = "Unprocessable request.") -> None:
        super().__init__(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=detail,
        )


class RateLimitError(HTTPException):
    def __init__(self, detail: str = "Rate limit exceeded. Please slow down.") -> None:
        super().__init__(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=detail)


class GoneError(HTTPException):
    """Used when a soft-deleted resource is accessed after retention period."""

    def __init__(self, resource: str = "Resource") -> None:
        super().__init__(
            status_code=status.HTTP_410_GONE,
            detail=f"{resource} has been permanently deleted.",
        )
