"""Live conformance twin for the real Azure adapters (see providers/azure.py).

Skipped entirely unless real credentials are present in the environment --
these hit actual vendor endpoints and cost real money (pytest.ini's `live`
marker exists exactly for this). Not run in CI; run manually with:

    AZURE_SPEECH_KEY=... AZURE_SPEECH_REGION=... \\
    AZURE_OPENAI_ENDPOINT=... AZURE_OPENAI_API_KEY=... AZURE_OPENAI_DEPLOYMENT=... \\
    pytest server/tests/conformance/test_azure_live.py -m live
"""

from __future__ import annotations

import os

import pytest
from app.providers.azure import AzureLLM, AzureSTT
from app.providers.types import AudioChunk, LLMConfig, Message, Role, STTConfig

pytestmark = pytest.mark.live

_HAS_SPEECH_CREDS = bool(
    os.environ.get("AZURE_SPEECH_KEY") and os.environ.get("AZURE_SPEECH_REGION")
)
_HAS_OPENAI_CREDS = bool(
    os.environ.get("AZURE_OPENAI_ENDPOINT")
    and os.environ.get("AZURE_OPENAI_API_KEY")
    and os.environ.get("AZURE_OPENAI_DEPLOYMENT")
)


async def _silence(n: int = 5):
    for i in range(n):
        yield AudioChunk(data=b"\x00" * 640, seq=i)


@pytest.mark.skipif(not _HAS_SPEECH_CREDS, reason="AZURE_SPEECH_KEY/REGION not set")
async def test_azure_stt_yields_one_final_on_silence() -> None:
    stt = AzureSTT(
        subscription_key=os.environ["AZURE_SPEECH_KEY"], region=os.environ["AZURE_SPEECH_REGION"]
    )
    results = [t async for t in stt.stream(_silence(), STTConfig())]
    assert len(results) == 1
    assert results[0].is_final
    await stt.aclose()


@pytest.mark.skipif(not _HAS_OPENAI_CREDS, reason="AZURE_OPENAI_* not set")
async def test_azure_llm_streams_a_real_reply() -> None:
    llm = AzureLLM(
        endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
        api_key=os.environ["AZURE_OPENAI_API_KEY"],
        deployment=os.environ["AZURE_OPENAI_DEPLOYMENT"],
    )
    messages = [Message(role=Role.USER, content="Say the word 'pineapple' and nothing else.")]
    deltas = [d async for d in llm.stream(messages, LLMConfig())]
    text = "".join(d.text for d in deltas)
    assert "pineapple" in text.lower()
    assert deltas[-1].finish_reason is not None
    await llm.aclose()
