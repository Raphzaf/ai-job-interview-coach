"""LLM provider abstraction + structured (JSON) output handling.

The RAG pipeline only talks to the `LLMProvider` protocol (messages in, text
out). `OpenAICompatibleProvider` covers OpenAI, Google Gemini, Groq, Mistral,
Ollama, LM Studio... because they all expose the OpenAI Chat Completions API;
switching provider is a matter of environment variables (LLM_BASE_URL,
LLM_MODEL, LLM_API_KEY). A provider with a different API would only need one
new class implementing `complete()`.

`generate_structured()` turns free-form LLM text into a validated Pydantic
object: it never returns unvalidated data.
"""

from __future__ import annotations

import json
import re
import time
from typing import Protocol, TypeVar

from pydantic import BaseModel, ValidationError

from app.core.config import Settings
from app.core.errors import LLMError
from app.core.logging import get_logger

logger = get_logger(__name__)

T = TypeVar("T", bound=BaseModel)
Message = dict[str, str]


class LLMProvider(Protocol):
    name: str

    def complete(self, messages: list[Message], json_mode: bool = True) -> str: ...


class OpenAICompatibleProvider:
    def __init__(self, settings: Settings):
        from openai import OpenAI

        self.model = settings.llm_model
        self.temperature = settings.llm_temperature
        self.name = f"{settings.llm_model} (OpenAI-compatible API)"
        self._client = OpenAI(
            api_key=settings.llm_api_key.get_secret_value() or "not-needed-for-local-servers",
            base_url=settings.llm_base_url or None,
            timeout=settings.llm_timeout_seconds,
            # One SDK-level retry handles transient 429/5xx; more would make the
            # UI hang for minutes before the offline fallback can kick in.
            max_retries=1,
        )
        self._json_mode_supported = True

    def complete(self, messages: list[Message], json_mode: bool = True) -> str:
        import openai

        kwargs: dict = {"model": self.model, "messages": messages, "temperature": self.temperature}
        if json_mode and self._json_mode_supported:
            # JSON mode makes the provider emit syntactically valid JSON. It does
            # not guarantee the *schema*, which is why Pydantic validation follows.
            kwargs["response_format"] = {"type": "json_object"}
        started = time.perf_counter()
        try:
            response = self._client.chat.completions.create(**kwargs)
        except openai.BadRequestError as exc:
            if "response_format" in kwargs:
                # Some OpenAI-compatible servers reject response_format; retry
                # without it and rely on the prompt + JSON extraction instead.
                logger.warning("Provider rejected JSON mode, retrying without it")
                self._json_mode_supported = False
                return self.complete(messages, json_mode=False)
            raise LLMError("The language model rejected the request.") from exc
        except openai.APITimeoutError as exc:
            raise LLMError("The language model timed out. Please try again.") from exc
        except openai.NotFoundError as exc:
            raise LLMError(f"Model '{self.model}' was not found by the provider (check LLM_MODEL / LLM_BASE_URL).") from exc
        except openai.AuthenticationError as exc:
            raise LLMError("The language model API key is invalid or missing (check LLM_API_KEY).") from exc
        except openai.APIError as exc:
            # Log the class and status only: the message may echo request content.
            logger.error("LLM provider error: %s (status=%s)", type(exc).__name__, getattr(exc, "status_code", "?"))
            raise LLMError("The language model service is unavailable right now.") from exc

        content = (response.choices[0].message.content or "") if response.choices else ""
        logger.info("LLM call completed in %.1fs (%d chars)", time.perf_counter() - started, len(content))
        if not content.strip():
            raise LLMError("The language model returned an empty response.")
        return content


_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)


def extract_json(text: str) -> dict:
    """Parse a JSON object from LLM text, tolerating markdown fences and chatter.

    Safe recovery only: we strip ```json fences and surrounding prose and parse
    the outermost {...}. We never "fix" the content itself (e.g. by guessing
    missing fields); that is left to validation and the repair round-trip.
    """
    cleaned = _FENCE_RE.sub("", text.strip())
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if start == -1 or end <= start:
            raise
        parsed = json.loads(cleaned[start : end + 1])
    if not isinstance(parsed, dict):
        raise json.JSONDecodeError("Expected a JSON object", cleaned, 0)
    return parsed


def generate_structured(provider: LLMProvider, system: str, user: str, schema: type[T], max_repairs: int = 1) -> T:
    """Call the LLM and return a validated `schema` instance or raise LLMError.

    If the first answer is not valid JSON or fails validation, the model gets
    ONE repair attempt with the exact validation error. Invalid output is never
    passed on: after the repair budget it is an LLMError (which the pipeline may
    turn into an explicitly-labelled offline fallback).
    """
    messages: list[Message] = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    last_error = ""
    for attempt in range(max_repairs + 1):
        raw = provider.complete(messages)
        try:
            return schema.model_validate(extract_json(raw))
        except json.JSONDecodeError as exc:
            last_error = f"Invalid JSON: {exc.msg}"
        except ValidationError as exc:
            # Keep only field locations and messages (no input values) for the log.
            last_error = "; ".join(f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors())
        logger.warning("Structured output invalid for %s (attempt %d): %s", schema.__name__, attempt + 1, last_error)
        messages += [
            {"role": "assistant", "content": raw},
            {
                "role": "user",
                "content": f"Your previous answer was not valid. Problem: {last_error}. "
                "Return ONLY the corrected JSON object that follows the required schema.",
            },
        ]
    raise LLMError(f"The language model returned an invalid {schema.__name__} ({last_error}).")


def build_llm_provider(settings: Settings) -> LLMProvider | None:
    """Return the configured provider, or None for offline mode."""
    if settings.llm_provider == "offline":
        return None
    if not settings.llm_is_configured:
        logger.warning("LLM_PROVIDER=openai_compatible but no LLM_API_KEY is set: running in offline mode.")
        return None
    return OpenAICompatibleProvider(settings)
