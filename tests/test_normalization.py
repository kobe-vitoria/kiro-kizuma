from kiro.application.normalization import normalize_text, tokenize


def test_normalize_collapses_whitespace():
    assert normalize_text("a   b\n\nc\t d") == "a b c d"


def test_normalize_trims():
    assert normalize_text("  hello  ") == "hello"


def test_normalize_truncates():
    assert normalize_text("abcdef", max_length=3) == "abc"


def test_normalize_handles_empty():
    assert normalize_text("") == ""
    assert normalize_text(None) == ""


def test_tokenize_lowercases_and_filters_short_words():
    tokens = tokenize("Erro ao logar no app")
    assert "erro" in tokens
    assert "logar" in tokens
    assert "app" in tokens
    assert "ao" not in tokens


def test_tokenize_filters_stopwords():
    tokens = tokenize("o erro de login")
    assert "o" not in tokens
    assert "de" not in tokens
    assert "erro" in tokens
    assert "login" in tokens


def test_tokenize_handles_accents():
    tokens = tokenize("conexão instável caiu")
    assert "conexão" in tokens
    assert "instável" in tokens
    assert "caiu" in tokens
