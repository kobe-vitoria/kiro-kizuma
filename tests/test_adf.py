from kiro.utils.adf import extract_text_from_adf


def test_returns_empty_for_none():
    assert extract_text_from_adf(None) == ""


def test_returns_empty_for_non_dict():
    assert extract_text_from_adf(42) == ""
    assert extract_text_from_adf([1, 2]) == ""


def test_extracts_text_node():
    assert extract_text_from_adf({"type": "text", "text": "Hello"}) == "Hello"


def test_extracts_nested_content():
    adf = {
        "type": "doc",
        "content": [
            {
                "type": "paragraph",
                "content": [
                    {"type": "text", "text": "Hello"},
                    {"type": "text", "text": "world"},
                ],
            },
            {"type": "paragraph", "content": [{"type": "text", "text": "again"}]},
        ],
    }
    out = extract_text_from_adf(adf)
    assert "Hello" in out
    assert "world" in out
    assert "again" in out


def test_handles_missing_content_key():
    assert extract_text_from_adf({"type": "doc"}) == ""


def test_ignores_unknown_node_types():
    adf = {
        "type": "doc",
        "content": [
            {"type": "mention", "attrs": {"id": "x"}},
            {"type": "text", "text": "ok"},
        ],
    }
    assert "ok" in extract_text_from_adf(adf)
