"""Clause-boundary chunking of streamed LLM output.

The largest latency win available in cascaded mode (LATENCY.md 5.4.1). Instead
of waiting for the model to finish and then synthesizing the whole reply, we
release each clause to TTS the moment it is complete. First audio starts while
the model is still generating.

Two things make this non-trivial:

1. **CJK has no spaces.** The primary language pack is Mandarin, so boundary
   detection cannot assume `". "` -- it must handle U+3002 and friends, which
   are unambiguous terminators needing no following whitespace.

2. **Tiny clauses cost more than they save.** Every chunk is a TTS round trip.
   Emitting "Ah." on its own adds connection overhead and produces audibly
   choppy prosody, so short fragments are held and merged forward.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Sentence-final punctuation only. Commas are deliberately excluded: they read
# as clause boundaries linguistically, but splitting TTS on every comma is
# exactly the "tiny clauses cost more than they save" failure mode this module
# exists to avoid. A pathologically long comma-heavy sentence is instead
# caught by the max_chars word-boundary fallback below.
_LATIN_TERMINATORS = frozenset(".!?")
_CJK_TERMINATORS = frozenset("。！？")

# Titles and abbreviations that precede a "." without ending the sentence.
# Checked against the word immediately before the period, case-insensitive.
# Not a sentence tokenizer -- a miss just costs slightly odd prosody, never a
# dropped word.
_ABBREVIATIONS = frozenset({
    "mr", "mrs", "ms", "dr", "prof", "sr", "jr", "st", "vs", "etc", "approx",
})


@dataclass(slots=True)
class ClauseChunker:
    """Accumulates deltas, releases complete clauses.

    Not thread-safe and not reusable across turns -- construct one per turn.
    """

    min_chars: int = 12
    max_chars: int = 240
    _buffer: str = field(default="", init=False)

    def feed(self, delta: str) -> list[str]:
        """Add generated text, return any clauses now ready for synthesis.

        Returns a list because one delta can complete more than one clause
        (models often emit several tokens' worth at once).
        """
        self._buffer += delta
        out: list[str] = []
        while (clause := self._take_clause()) is not None:
            out.append(clause)
        return out

    def flush(self) -> str | None:
        """Release whatever remains at end of generation.

        Must be called when the LLM stream finishes, or the final clause -- which
        frequently has no terminating punctuation -- is silently dropped.
        """
        remainder = self._buffer.strip()
        self._buffer = ""
        return remainder or None

    def _take_clause(self) -> str | None:
        idx = self._find_boundary()
        if idx is None:
            # Runaway clause with no punctuation: release at a word boundary
            # rather than letting the buffer grow without bound.
            if len(self._buffer) >= self.max_chars:
                return self._take_at_word_break()
            return None

        clause = self._buffer[: idx + 1]
        self._buffer = self._buffer[idx + 1 :].lstrip()
        return clause.strip()

    def _find_boundary(self) -> int | None:
        """Index of the first usable terminator, or None."""
        for i, ch in enumerate(self._buffer):
            if i + 1 < self.min_chars:
                continue  # too short to be worth a TTS call

            if ch in _CJK_TERMINATORS:
                return i

            if ch in _LATIN_TERMINATORS:
                nxt = self._buffer[i + 1] if i + 1 < len(self._buffer) else ""
                if not nxt:
                    return None  # may still be mid-token; wait for more
                if not nxt.isspace():
                    continue  # "3.14" -- not a clause end
                if ch == "." and self._preceding_word_is_abbreviation(i):
                    continue  # "Dr. Chen" -- not a clause end
                return i
        return None

    def _preceding_word_is_abbreviation(self, period_idx: int) -> bool:
        start = period_idx
        while start > 0 and self._buffer[start - 1].isalpha():
            start -= 1
        return self._buffer[start:period_idx].lower() in _ABBREVIATIONS

    def _take_at_word_break(self) -> str:
        window = self._buffer[: self.max_chars]
        cut = window.rfind(" ")
        if cut <= 0:
            cut = self.max_chars  # CJK or one very long token
        clause = self._buffer[:cut]
        self._buffer = self._buffer[cut:].lstrip()
        return clause.strip()
