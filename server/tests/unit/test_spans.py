import pytest
from app.telemetry.spans import LatencyReport, Mark, TurnTimeline, percentile


class TestTurnTimeline:
    def test_ttfa_measures_speech_end_to_first_audio(self) -> None:
        t = TurnTimeline(turn_id="t1")
        t.marks[Mark.SPEECH_END.value] = 0.0
        t.marks[Mark.FIRST_AUDIO_OUT.value] = 0.9
        assert t.ttfa_ms == pytest.approx(900.0)

    def test_ttfa_none_when_marks_missing(self) -> None:
        t = TurnTimeline(turn_id="t1")
        assert t.ttfa_ms is None

    def test_second_mark_call_does_not_overwrite(self) -> None:
        t = TurnTimeline(turn_id="t1")
        t.mark(Mark.SPEECH_END)
        first = t.marks[Mark.SPEECH_END.value]
        t.mark(Mark.SPEECH_END)
        assert t.marks[Mark.SPEECH_END.value] == first

    def test_stage_durations_omits_missing_stages(self) -> None:
        t = TurnTimeline(turn_id="t1")
        t.marks[Mark.SPEECH_END.value] = 0.0
        t.marks[Mark.STT_FINAL.value] = 0.1
        stages = t.stage_durations_ms()
        assert "stt_finalize" in stages
        assert "llm_ttft" not in stages

    def test_summary_reports_barge_in_flag(self) -> None:
        t = TurnTimeline(turn_id="t1", barged_in=True)
        assert t.summary()["barged_in"] is True


class TestPercentile:
    def test_p50_of_sorted_range(self) -> None:
        values = [float(i) for i in range(1, 101)]  # 1..100
        assert percentile(values, 50) == pytest.approx(50, abs=1)

    def test_p95_biased_toward_high_end(self) -> None:
        values = [float(i) for i in range(1, 101)]
        assert percentile(values, 95) >= 94

    def test_single_value(self) -> None:
        assert percentile([42.0], 50) == 42.0
        assert percentile([42.0], 95) == 42.0

    def test_empty_raises(self) -> None:
        with pytest.raises(ValueError):
            percentile([], 50)


class TestLatencyReport:
    def test_ignores_turns_without_ttfa(self) -> None:
        report = LatencyReport()
        incomplete = TurnTimeline(turn_id="a")
        report.add(incomplete)
        assert report.stats() == {"n": 0}

    def test_aggregates_multiple_turns(self) -> None:
        report = LatencyReport()
        for ms in (500.0, 700.0, 900.0, 1100.0):
            t = TurnTimeline(turn_id="x")
            t.marks[Mark.SPEECH_END.value] = 0.0
            t.marks[Mark.FIRST_AUDIO_OUT.value] = ms / 1000.0
            report.add(t)
        stats = report.stats()
        assert stats["n"] == 4
        assert stats["p50"] > 0
        assert stats["max"] == pytest.approx(1100.0)
