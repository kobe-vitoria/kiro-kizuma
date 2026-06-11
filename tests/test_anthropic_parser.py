import pytest

from kiro.application.generation.anthropic_provider import AnthropicProvider
from kiro.domain.exceptions import LLMResponseError


def test_parse_valid_json():
    raw = """{
      "title": "T",
      "problem": "P",
      "cause": "C",
      "solution": "1. a\\n2. b",
      "faq": [{"question": "q?", "answer": "a"}],
      "tags": ["x"]
    }"""
    article = AnthropicProvider._parse_response(raw)
    assert article.title == "T"
    assert article.faq[0].question == "q?"


def test_parse_strips_markdown_fences():
    raw = (
        "```json\n"
        '{"title":"T","problem":"P","cause":"C","solution":"1. a"}\n'
        "```"
    )
    article = AnthropicProvider._parse_response(raw)
    assert article.title == "T"


def test_invalid_json_raises():
    with pytest.raises(LLMResponseError):
        AnthropicProvider._parse_response("isto não é json")


def test_missing_required_field_raises():
    with pytest.raises(LLMResponseError):
        AnthropicProvider._parse_response('{"title": "x"}')


def test_empty_string_fields_raise():
    raw = '{"title": "", "problem": "p", "cause": "c", "solution": "s"}'
    with pytest.raises(LLMResponseError):
        AnthropicProvider._parse_response(raw)
