import pytest

from paperforge.services.agentic.json_utils import parse_json_object


def test_parse_json_object_accepts_fence_and_preamble() -> None:
    assert parse_json_object('```json\n{"score": 80}\n```') == {"score": 80}
    assert parse_json_object('Result: {"score": 70}') == {"score": 70}


def test_parse_json_object_rejects_non_object() -> None:
    with pytest.raises(ValueError):
        parse_json_object("[1, 2]")
