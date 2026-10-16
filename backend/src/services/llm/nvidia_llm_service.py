"""
NVIDIA NIM chat-completion client (OpenAI-compatible).

Features: shared async HTTP client, retries on transient errors, streaming,
JSON-mode helper with robust extraction, token-usage capture, and a cheap
"fast" model for routing / planning.
"""

from __future__ import annotations

import asyncio
import json
import re
from typing import Any, AsyncGenerator, Dict, List, Optional

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from src.core.config import settings
from src.core.logger import get_logger, log_timing

logger = get_logger(__name__)

Message = Dict[str, str]


class LLMError(RuntimeError):
    pass


class LLMUsage:
    """Accumulates token usage for one request / trace."""

    def __init__(self) -> None:
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.calls = 0

    def add(self, usage: Optional[Dict[str, Any]]) -> None:
        if not usage:
            return
        self.prompt_tokens += int(usage.get("prompt_tokens") or 0)
        self.completion_tokens += int(usage.get("completion_tokens") or 0)
        self.calls += 1

    def to_dict(self) -> Dict[str, int]:
        return {
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.prompt_tokens + self.completion_tokens,
            "llm_calls": self.calls,
        }


_JSON_BLOCK = re.compile(r"```(?:json)?\s*(\{.*?\}|\[.*?\])\s*```", re.DOTALL)


def extract_json(text: str) -> Any:
    """Pull the first JSON object/array out of an LLM response."""
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    m = _JSON_BLOCK.search(text)
    if m:
        return json.loads(m.group(1))
    # Fallback: first { ... last }
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end > start:
        return json.loads(text[start:end + 1])
    raise ValueError("No JSON found in LLM response")


class NvidiaLLMService:
    _shared_client: Optional[httpx.AsyncClient] = None

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        fast_model: Optional[str] = None,
    ):
        self.api_key = api_key or settings.nvidia_api_key
        self.base_url = base_url or settings.nvidia_base_url
        self.model = model or settings.nvidia_llm_model
        self.fast_model = fast_model or settings.nvidia_llm_fast_model or self.model
        self.timeout = settings.nvidia_timeout

    # ── HTTP ────────────────────────────────────────────────────────────

    def _client(self) -> httpx.AsyncClient:
        cls = type(self)
        if cls._shared_client is None or cls._shared_client.is_closed:
            cls._shared_client = httpx.AsyncClient(
                base_url=self.base_url,
                headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                timeout=httpx.Timeout(self.timeout, connect=10.0),
            )
        return cls._shared_client

    @classmethod
    async def aclose(cls) -> None:
        if cls._shared_client is not None and not cls._shared_client.is_closed:
            await cls._shared_client.aclose()
        cls._shared_client = None

    @staticmethod
    def _build_messages(
        prompt: str, system_prompt: Optional[str], chat_history: Optional[List[Message]]
    ) -> List[Message]:
        messages: List[Message] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        if chat_history:
            messages.extend({"role": m["role"], "content": m["content"]} for m in chat_history if m.get("content"))
        messages.append({"role": "user", "content": prompt})
        return messages

    # ── Non-streaming ───────────────────────────────────────────────────

    def _model_chain(self, model: str) -> List[str]:
        chain = [model] + [m for m in settings.nvidia_llm_fallback_list if m != model]
        return chain

    async def _post_with_fallback(self, payload: Dict[str, Any], json_mode: bool = False) -> httpx.Response:
        """POST /chat/completions, degrading JSON mode and falling back on 404/410/429."""
        last: Optional[httpx.Response] = None
        for model in self._model_chain(payload["model"]):
            payload["model"] = model
            response = await self._client().post("/chat/completions", json=payload)
            if response.status_code in (400, 422) and "response_format" in payload:
                payload.pop("response_format", None)
                response = await self._client().post("/chat/completions", json=payload)
            if response.status_code < 400:
                if model != self.model and model != self.fast_model:
                    logger.warning("LLM fallback model used", model=model)
                return response
            last = response
            if response.status_code not in (404, 410, 429, 503):
                break
            logger.warning("LLM model unavailable, trying fallback", model=model, status=response.status_code)
        assert last is not None
        raise LLMError(f"NIM error {last.status_code}: {last.text[:300]}")

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        retry=retry_if_exception_type((httpx.TimeoutException, httpx.NetworkError)),
        reraise=True,
    )
    async def chat(
        self,
        messages: List[Message],
        model: Optional[str] = None,
        max_tokens: int = 1024,
        temperature: float = 0.3,
        top_p: float = 0.9,
        usage: Optional[LLMUsage] = None,
        json_mode: bool = False,
    ) -> str:
        if not self.api_key:
            raise LLMError("NVIDIA_API_KEY is not configured")
        payload: Dict[str, Any] = {
            "model": model or self.model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "top_p": top_p,
            "stream": False,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        response = await self._post_with_fallback(payload, json_mode=json_mode)
        data = response.json()
        if usage is not None:
            usage.add(data.get("usage"))
        return data["choices"][0]["message"]["content"] or ""

    @log_timing("llm_generate")
    async def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        chat_history: Optional[List[Message]] = None,
        max_tokens: int = 1024,
        temperature: float = 0.3,
        top_p: float = 0.9,
        fast: bool = False,
        usage: Optional[LLMUsage] = None,
    ) -> str:
        messages = self._build_messages(prompt, system_prompt, chat_history)
        return await self.chat(
            messages, model=self.fast_model if fast else self.model,
            max_tokens=max_tokens, temperature=temperature, top_p=top_p, usage=usage,
        )

    async def generate_json(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        max_tokens: int = 1024,
        temperature: float = 0.1,
        fast: bool = True,
        usage: Optional[LLMUsage] = None,
        retries: int = 1,
    ) -> Any:
        """Ask for JSON and parse it, retrying once with a stricter instruction."""
        messages = self._build_messages(prompt, system_prompt, None)
        last_error: Optional[Exception] = None
        for attempt in range(retries + 1):
            text = await self.chat(
                messages, model=self.fast_model if fast else self.model,
                max_tokens=max_tokens, temperature=temperature, usage=usage, json_mode=True,
            )
            try:
                return extract_json(text)
            except (ValueError, json.JSONDecodeError) as exc:
                last_error = exc
                messages.append({"role": "assistant", "content": text})
                messages.append({"role": "user", "content": "That was not valid JSON. Reply with ONLY the JSON object."})
        raise LLMError(f"Could not parse JSON from model: {last_error}")

    # ── Streaming ───────────────────────────────────────────────────────

    async def stream(
        self,
        messages: List[Message],
        model: Optional[str] = None,
        max_tokens: int = 1024,
        temperature: float = 0.3,
        top_p: float = 0.9,
        usage: Optional[LLMUsage] = None,
    ) -> AsyncGenerator[str, None]:
        if not self.api_key:
            raise LLMError("NVIDIA_API_KEY is not configured")
        payload = {
            "model": model or self.model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "top_p": top_p,
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        chain = self._model_chain(payload["model"])
        for attempt, model_name in enumerate(chain):
            payload["model"] = model_name
            async with self._client().stream("POST", "/chat/completions", json=payload) as response:
                if response.status_code >= 400:
                    body = await response.aread()
                    if response.status_code in (404, 410, 429, 503) and attempt < len(chain) - 1:
                        logger.warning("LLM stream model unavailable, trying fallback", model=model_name, status=response.status_code)
                        continue
                    raise LLMError(f"NIM error {response.status_code}: {body[:300]!r}")
                async for token in self._iter_sse(response, usage):
                    yield token
                return

    async def _iter_sse(self, response: httpx.Response, usage: Optional[LLMUsage]) -> AsyncGenerator[str, None]:
        if True:
            async for line in response.aiter_lines():
                if not line.startswith("data: "):
                    continue
                data_str = line[6:].strip()
                if data_str == "[DONE]":
                    break
                try:
                    data = json.loads(data_str)
                except json.JSONDecodeError:
                    continue
                if usage is not None and data.get("usage"):
                    usage.add(data["usage"])
                choices = data.get("choices") or []
                if not choices:
                    continue
                content = (choices[0].get("delta") or {}).get("content")
                if content:
                    yield content

    async def generate_stream(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        chat_history: Optional[List[Message]] = None,
        max_tokens: int = 1024,
        temperature: float = 0.3,
        top_p: float = 0.9,
        usage: Optional[LLMUsage] = None,
    ) -> AsyncGenerator[str, None]:
        messages = self._build_messages(prompt, system_prompt, chat_history)
        async for token in self.stream(messages, max_tokens=max_tokens, temperature=temperature, top_p=top_p, usage=usage):
            yield token

    async def generate_with_context(
        self, query: str, context: str, system_prompt: Optional[str] = None, max_tokens: int = 1024,
    ) -> AsyncGenerator[str, None]:
        """Backward-compatible helper used by the legacy agents."""
        default_system = (
            "You are a helpful AI assistant. Answer the user's question based on the provided context. "
            "If the context doesn't contain relevant information, say so. Cite the context when relevant."
        )
        prompt = f"Context:\n{context}\n\nQuestion: {query}\n\nAnswer:"
        async for token in self.generate_stream(prompt, system_prompt=system_prompt or default_system, max_tokens=max_tokens):
            yield token


_default_llm: Optional[NvidiaLLMService] = None


def get_llm_service() -> NvidiaLLMService:
    global _default_llm
    if _default_llm is None:
        _default_llm = NvidiaLLMService()
    return _default_llm


def set_llm_service(service: Optional[NvidiaLLMService]) -> None:
    """Dependency override hook (tests, alternative providers)."""
    global _default_llm
    _default_llm = service
