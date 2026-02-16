import pytest

from handlers.transcode import handler as transcode_handler
from handlers.image_processing import handler as image_handler


def test_transcode_handler_returns_dict() -> None:
    event = {"bucket": "test-bucket", "key": "video.mp4"}
    result = transcode_handler(event, None)
    assert isinstance(result, dict)
    assert result.get("status") == "ok"
    assert result.get("handler") == "transcode"
    assert result.get("bucket") == "test-bucket"
    assert result.get("key") == "video.mp4"


def test_transcode_handler_empty_event() -> None:
    result = transcode_handler({}, None)
    assert result.get("status") == "ok"


def test_image_processing_handler_returns_dict() -> None:
    event = {"bucket": "img-bucket", "key": "photo.jpg", "action": "thumbnail"}
    result = image_handler(event, None)
    assert isinstance(result, dict)
    assert result.get("status") == "ok"
    assert result.get("handler") == "image_processing"
    assert result.get("action") == "thumbnail"


def test_image_processing_handler_default_action() -> None:
    result = image_handler({}, None)
    assert result.get("action") == "resize"
