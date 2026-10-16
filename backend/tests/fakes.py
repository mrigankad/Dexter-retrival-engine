"""Deterministic fakes so the whole engine runs with no network access."""

from __future__ import annotations

import hashlib
import math
import re
from typing import Any, AsyncGenerator, Dict, List, Optional

from src.services.llm.embedding_service import EmbeddingService
from src.services.llm.nvidia_llm_service import LLMUsage, NvidiaLLMService
from src.services.llm.reranker_service import RerankerService

_WORD = re.compile(r"[a-z0-9]+")


class FakeEmbeddingService(EmbeddingService):
    """Bag-of-hashed-words embedding: similar texts → similar vectors. Dimension 64."""

    dim = 64

    def __init__(self, dim: int = 64):
        super().__init__(api_key="fake", model="fake-embed")
        self.dim = dim
        self.calls = 0

    def _vec(self, text: str) -> List[float]:
        v = [0.0] * self.dim
        for w in _WORD.findall(text.lower()):
            h = int(hashlib.md5(w.encode()).hexdigest(), 16)
            v[h % self.dim] += 1.0
            v[(h // 7) % self.dim] += 0.5
        norm = math.sqrt(sum(x * x for x in v)) or 1.0
        return [x / norm for x in v]

    async def _embed_batch(self, texts: List[str], input_type: str) -> List[List[float]]:
        self.calls += 1
        return [self._vec(t) for t in texts]


class FakeReranker(RerankerService):
    """Lexical-overlap reranker (no model)."""

    def __init__(self):
        super().__init__(backend="nvidia", model_name="fake-rerank")

    async def _rerank_nvidia(self, query: str, documents: List[str]):
        q = set(_WORD.findall(query.lower()))
        out = []
        for i, d in enumerate(documents):
            dt = set(_WORD.findall(d.lower()))
            out.append((i, d, len(q & dt) / (len(q) or 1)))
        return out


class FakeLLM(NvidiaLLMService):
    """Scripted LLM. ``responses`` maps a substring of the prompt → reply; default echoes context."""

    def __init__(self, responses: Optional[Dict[str, str]] = None, default: str = "FAKE ANSWER [1]"):
        super().__init__(api_key="fake", model="fake-llm", fast_model="fake-llm-fast")
        self.responses = responses or {}
        self.default = default
        self.calls: List[Dict[str, Any]] = []

    def _reply(self, messages: List[Dict[str, str]]) -> str:
        text = "\n".join(m["content"] for m in messages)
        for key, value in self.responses.items():
            if key in text:
                return value
        return self.default

    async def chat(self, messages, model=None, max_tokens=1024, temperature=0.3, top_p=0.9, usage: Optional[LLMUsage] = None, json_mode=False) -> str:
        self.calls.append({"model": model or self.model, "messages": messages, "json_mode": json_mode})
        if usage is not None:
            usage.add({"prompt_tokens": 10, "completion_tokens": 5})
        return self._reply(messages)

    async def stream(self, messages, model=None, max_tokens=1024, temperature=0.3, top_p=0.9, usage: Optional[LLMUsage] = None) -> AsyncGenerator[str, None]:
        self.calls.append({"model": model or self.model, "messages": messages, "stream": True})
        reply = self._reply(messages)
        if usage is not None:
            usage.add({"prompt_tokens": 10, "completion_tokens": len(reply.split())})
        for word in reply.split(" "):
            yield word + " "
