from app.pipeline.chunker import ClauseChunker


def feed_all(chunker: ClauseChunker, deltas: list[str]) -> list[str]:
    out: list[str] = []
    for d in deltas:
        out.extend(chunker.feed(d))
    if (rest := chunker.flush()) is not None:
        out.append(rest)
    return out


def test_releases_clause_on_terminator_with_trailing_space() -> None:
    c = ClauseChunker(min_chars=1)
    clauses = feed_all(c, ["Hello there. ", "How are you?"])
    assert clauses == ["Hello there.", "How are you?"]


def test_holds_below_min_chars() -> None:
    c = ClauseChunker(min_chars=20)
    # "Ah." is well under min_chars, should not release until flush
    clauses = feed_all(c, ["Ah. That is interesting, tell me more."])
    assert clauses == ["Ah. That is interesting, tell me more."]


def test_does_not_split_on_decimal_or_abbreviation() -> None:
    c = ClauseChunker(min_chars=1)
    clauses = feed_all(c, ["Pi is 3.14 and Dr. Chen agrees."])
    assert clauses == ["Pi is 3.14 and Dr. Chen agrees."]


def test_cjk_terminator_needs_no_trailing_space() -> None:
    c = ClauseChunker(min_chars=1)
    clauses = feed_all(c, ["你好。", "你今天怎么样？"])
    assert clauses == ["你好。", "你今天怎么样？"]


def test_one_delta_can_complete_multiple_clauses() -> None:
    c = ClauseChunker(min_chars=1)
    clauses = c.feed("One. Two. Three.")
    assert clauses == ["One.", "Two."]
    assert c.flush() == "Three."


def test_flush_returns_none_when_buffer_empty() -> None:
    c = ClauseChunker()
    assert c.flush() is None


def test_runaway_clause_releases_at_word_boundary() -> None:
    c = ClauseChunker(min_chars=1, max_chars=30)
    long_text = "word " * 20  # no terminators at all, 100 chars
    clauses = feed_all(c, [long_text])
    assert clauses  # at least one forced release happened
    assert all(len(cl) <= 30 or " " not in cl for cl in clauses[:-1])
    assert "".join(clauses).replace(" ", "") == long_text.replace(" ", "")


def test_no_word_break_falls_back_to_hard_cut() -> None:
    c = ClauseChunker(min_chars=1, max_chars=10)
    clauses = feed_all(c, ["一二三四五六七八九十十一十二十三"])
    assert clauses
    assert "".join(clauses) == "一二三四五六七八九十十一十二十三"


def test_partial_terminator_at_end_of_delta_waits_for_more() -> None:
    c = ClauseChunker(min_chars=1)
    # A "." with nothing after it yet is ambiguous (could be "3." before "14"),
    # so it must not release until either more text or flush() disambiguates it.
    assert c.feed("The value is 3.") == []
    assert c.feed("14 exactly.") == []
    assert c.flush() == "The value is 3.14 exactly."


def test_does_not_split_after_title_abbreviation() -> None:
    c = ClauseChunker(min_chars=1)
    clauses = feed_all(c, ["Dr. Chen will see you now."])
    assert clauses == ["Dr. Chen will see you now."]
