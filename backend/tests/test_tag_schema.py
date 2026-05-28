"""
Tests for tag schema validation.
"""
import pytest
from pydantic import ValidationError

from app.schemas.tag import TagCreateIn, TagUpdateIn


class TestTagCreateIn:
    def test_valid_hex_color(self):
        t = TagCreateIn(name="Tech", color="#1a2b3c")
        assert t.color == "#1a2b3c"

    def test_color_lowercased(self):
        t = TagCreateIn(name="Tech", color="#AABBCC")
        assert t.color == "#aabbcc"

    def test_invalid_color_raises(self):
        with pytest.raises(ValidationError):
            TagCreateIn(name="Tech", color="red")

    def test_invalid_short_hex_raises(self):
        with pytest.raises(ValidationError):
            TagCreateIn(name="Tech", color="#fff")

    def test_default_color(self):
        t = TagCreateIn(name="Tech")
        assert t.color == "#6366f1"


class TestTagUpdateIn:
    def test_all_none_is_valid(self):
        t = TagUpdateIn()
        assert t.name is None
        assert t.color is None

    def test_none_color_passes_through(self):
        t = TagUpdateIn(color=None)
        assert t.color is None

    def test_invalid_color_still_raises(self):
        with pytest.raises(ValidationError):
            TagUpdateIn(color="blue")
