"""Reproducible latency replay (PRD EV-4).

Runs N synthetic turns through the real cascaded pipeline (`app.pipeline.
cascaded.run_turn`) with mock providers configured to the per-stage latency
distributions modelled in LATENCY.md Sec 5.2, and aggregates the resulting
`TurnTimeline`s into a `LatencyReport`. Every distribution is seeded
(`LatencyProfile.sample` draws from a seeded `random.Random`), so the same
`n` and `seed` always request the same sleep durations -- turning "did this
change regress TTFA" into a reproducible CI check instead of something that
can only be observed against noisy real traffic.

"Reproducible" is about those requested durations, not bit-exact observed
wall-clock time: `asyncio.sleep(x)` is a lower bound, not an exact wait, so
two runs with an identical seed still carry a few ms of real event-loop
scheduling jitter in their measured `perf_counter` timestamps. A CI gate
comparing against this replay's numbers should use a tolerance, not exact
equality -- see test_latency_replay.py's determinism test for the size of
that tolerance in practice.

Target distributions are pinned here, independent of mock.py's own defaults
(which exist for unrelated unit tests) -- a change to those defaults must not
silently drift the numbers this replay is supposed to hold constant.
"""

from __future__ import annotations

from app.pipeline.cascaded import run_turn
from app.pipeline.chunker import ClauseChunker
from app.providers.mock import LatencyProfile, MockLLM, MockTTS, scripted_tutor
from app.providers.types import LLMConfig, Message, Role, TTSConfig
from app.telemetry.spans import LatencyReport, Mark, TurnTimeline

# Cascaded-mode per-stage targets, LATENCY.md 5.2.
TTFT_PROFILE = LatencyProfile(mean_ms=300.0, stdev_ms=40.0)
INTER_TOKEN_PROFILE = LatencyProfile(mean_ms=18.0, stdev_ms=4.0)
TTS_TTFB_PROFILE = LatencyProfile(mean_ms=180.0, stdev_ms=25.0)

# MockTTS's realtime_factor exists to model realistic playback pacing for
# jitter-buffer tests elsewhere (mock.py's own default is 0.35). TTFA is
# marked exactly once, on the FIRST synthesized chunk (see cascaded.py) --
# every clause after that is irrelevant to the number this module measures,
# so simulating their playback pacing here would only add real wall-clock
# sleep time with zero effect on the statistic. 0.0 disables it.
_REPLAY_REALTIME_FACTOR = 0.0


async def replay_turns(
    n: int,
    seed: int = 0,
    reply_text: str = "That sounds good. Tell me more about that, please.",
) -> LatencyReport:
    """Run `n` synthetic turns and return their aggregated TTFA stats."""
    report = LatencyReport()
    for i in range(n):
        timeline = TurnTimeline(turn_id=str(i))
        timeline.mark(Mark.SPEECH_END)
        timeline.mark(Mark.PROMPT_READY)

        llm = MockLLM(
            responder=scripted_tutor([reply_text]),
            ttft=TTFT_PROFILE,
            inter_token=INTER_TOKEN_PROFILE,
            seed=seed + i,
        )
        tts = MockTTS(
            ttfb=TTS_TTFB_PROFILE, realtime_factor=_REPLAY_REALTIME_FACTOR, seed=seed + i
        )

        async for _ in run_turn(
            llm,
            tts,
            [Message(role=Role.USER, content="hi")],
            LLMConfig(),
            TTSConfig(),
            timeline,
            chunker=ClauseChunker(),
        ):
            pass

        report.add(timeline)

    return report
