"""Real Azure adapters: Azure AI Speech (STT) and Azure OpenAI (LLM).

Everything else in this project runs on deterministic mocks (ADR-003) --
these are the first real vendor calls. Both implement the same `Protocol`
contracts as their mock counterparts (see protocols.py), so nothing upstream
(the orchestrator, the gateway) needs to know which kind it was handed.

Not covered by the CI conformance suite (test_provider_conformance.py) --
that suite is deliberately mock-only so it runs with no credentials and no
spend. These carry a `@pytest.mark.live` twin instead (see
tests/conformance/test_azure_live.py), skipped unless real credentials are
present in the environment.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass, field

import azure.cognitiveservices.speech as speechsdk
from openai import AsyncAzureOpenAI

from app.providers.types import (
    AudioChunk,
    LLMConfig,
    LLMDelta,
    Message,
    STTConfig,
    Transcript,
)

logger = logging.getLogger("parlons.azure")

_DEFAULT_CONFIDENCE = 0.9
"""Used when the recognizer doesn't return a parseable per-word confidence
(only the detailed-output-format JSON carries one, and even then only when
Azure's NBest list is non-empty). Better than fabricating false precision."""


@dataclass
class AzureSTT:
    """One-shot recognition per `stream()` call via Azure AI Speech.

    The orchestrator only ever calls `stream()` with a *complete*, already-
    buffered utterance (see `SessionOrchestrator.on_speech_end`: it puts a
    `None` sentinel onto the audio queue before calling `stt.stream()`, so
    the iterator this consumes is finite and already fully available). That
    means there is no live-pacing benefit to Azure's continuous-recognition
    events here -- `recognize_once` after writing all the audio is simpler
    and exactly matches what's actually being asked of it.

    Consequence: no interim results are ever yielded, regardless of
    `config.interim_results` -- there is nothing partial to report once the
    whole utterance is already in hand.
    """

    subscription_key: str
    region: str
    name: str = "azure-speech-stt"

    async def stream(
        self,
        audio: AsyncIterator[AudioChunk],
        config: STTConfig,
    ) -> AsyncIterator[Transcript]:
        stream_format = speechsdk.audio.AudioStreamFormat(
            samples_per_second=config.sample_rate, bits_per_sample=16, channels=1
        )
        push_stream = speechsdk.audio.PushAudioInputStream(stream_format=stream_format)
        total_bytes = 0
        async for chunk in audio:
            push_stream.write(chunk.data)
            total_bytes += len(chunk.data)
        push_stream.close()
        duration_ms = total_bytes / (config.sample_rate * 2) * 1000
        logger.info("azure_stt: received %d bytes (%.0fms) of audio", total_bytes, duration_ms)

        speech_config = speechsdk.SpeechConfig(
            subscription=self.subscription_key, region=self.region
        )
        speech_config.speech_recognition_language = config.language
        speech_config.output_format = speechsdk.OutputFormat.Detailed
        audio_config = speechsdk.audio.AudioConfig(stream=push_stream)
        recognizer = speechsdk.SpeechRecognizer(
            speech_config=speech_config, audio_config=audio_config
        )

        if config.phrase_hints:
            phrase_list = speechsdk.PhraseListGrammar.from_recognizer(recognizer)
            for phrase in config.phrase_hints:
                phrase_list.addPhrase(phrase)

        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, recognizer.recognize_once)

        text = ""
        confidence = 0.0
        if result.reason == speechsdk.ResultReason.RecognizedSpeech:
            text = result.text
            confidence = _confidence_from_detailed_json(result.json) or _DEFAULT_CONFIDENCE
        logger.info("azure_stt: result.reason=%s text=%r", result.reason, text)

        yield Transcript(text=text, is_final=True, confidence=confidence, language=config.language)

    async def aclose(self) -> None:
        return None


def _confidence_from_detailed_json(raw: str) -> float | None:
    """Best-effort extraction from Detailed-format recognition JSON.

    Returns None on anything unexpected -- a missing confidence score must
    never take down a turn (same principle as PronunciationProvider.assess)."""
    try:
        best = json.loads(raw).get("NBest") or []
        return float(best[0]["Confidence"]) if best else None
    except (ValueError, KeyError, IndexError, TypeError):
        return None


@dataclass
class AzureLLM:
    """Streaming chat completion via Azure OpenAI.

    One client, created lazily and reused across turns -- re-establishing
    TLS per turn would be wasteful for a long-running session."""

    endpoint: str
    api_key: str
    deployment: str
    api_version: str = "2024-10-21"
    name: str = "azure-openai-llm"
    _client: AsyncAzureOpenAI | None = field(default=None, init=False, repr=False)

    def _get_client(self) -> AsyncAzureOpenAI:
        if self._client is None:
            self._client = AsyncAzureOpenAI(
                azure_endpoint=self.endpoint,
                api_key=self.api_key,
                api_version=self.api_version,
            )
        return self._client

    async def stream(
        self,
        messages: Sequence[Message],
        config: LLMConfig,
    ) -> AsyncIterator[LLMDelta]:
        client = self._get_client()
        oai_messages = [{"role": m.role.value, "content": m.content} for m in messages]
        input_chars = sum(len(m.content) for m in messages)
        emitted_chars = 0

        response = await client.chat.completions.create(
            model=self.deployment,
            messages=oai_messages,  # type: ignore[arg-type]
            temperature=config.temperature,
            max_tokens=config.max_output_tokens,
            stream=True,
        )
        async for event in response:  # type: ignore[union-attr]
            if not event.choices:
                continue
            choice = event.choices[0]
            delta_text = choice.delta.content or ""
            if delta_text:
                emitted_chars += len(delta_text)
                yield LLMDelta(text=delta_text)
            if choice.finish_reason:
                yield LLMDelta(
                    finish_reason=choice.finish_reason,
                    input_tokens=input_chars // 4,
                    output_tokens=emitted_chars // 4,
                )

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.close()
            self._client = None
