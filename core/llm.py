# Pluggable LLM backend — Groq (primary), Gemini (fallback), Ollama (offline)
# All backends use KeyRotator for automatic key rotation on rate limits.

import base64
import logging
from abc import ABC, abstractmethod
from typing import Generator

import settings
from core import key_rotator as kr

log = logging.getLogger(__name__)


class LLMBackend(ABC):
    @abstractmethod
    def chat(self, messages: list, tools: list = None, stream: bool = False) -> str | Generator:
        pass

    @abstractmethod
    def vision(self, image_path: str, prompt: str) -> str:
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        pass


class GroqBackend(LLMBackend):
    @property
    def name(self):
        return "groq"

    def _client(self, key: str):
        from groq import Groq
        return Groq(api_key=key)

    def chat(self, messages: list, tools: list = None, stream: bool = False) -> str:
        import groq as groq_lib
        last_err = None
        for _ in range(kr._rotators["groq"].total_count() or 1):
            key = kr.get("groq")
            if not key:
                raise RuntimeError("All Groq API keys exhausted")
            try:
                client = self._client(key)
                kwargs = {
                    "model": settings.GROQ_VOICE_MODEL,
                    "messages": messages,
                    "temperature": 0.7,
                    "max_tokens": 1024,
                }
                if tools:
                    kwargs["tools"] = tools
                    kwargs["tool_choice"] = "auto"
                if stream:
                    kwargs["stream"] = True
                    return self._stream(client, kwargs)
                response = client.chat.completions.create(**kwargs)
                kr.mark_ok("groq", key)
                return self._parse(response)
            except groq_lib.RateLimitError as e:
                kr.mark_failed("groq", key, "rate limit")
                last_err = e
            except groq_lib.AuthenticationError as e:
                kr.mark_failed("groq", key, "auth error")
                last_err = e
            except Exception as e:
                last_err = e
                break
        raise last_err or RuntimeError("Groq chat failed")

    def _stream(self, client, kwargs) -> Generator:
        for chunk in client.chat.completions.create(**kwargs):
            delta = chunk.choices[0].delta
            if delta.content:
                yield delta.content

    def _parse(self, response):
        msg = response.choices[0].message
        if msg.tool_calls:
            return msg
        return msg.content or ""

    def vision(self, image_path: str, prompt: str) -> str:
        import groq as groq_lib
        with open(image_path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode()
        last_err = None
        for _ in range(kr._rotators["groq"].total_count() or 1):
            key = kr.get("groq")
            if not key:
                raise RuntimeError("All Groq API keys exhausted")
            try:
                client = self._client(key)
                response = client.chat.completions.create(
                    model=settings.GROQ_VISION_MODEL,
                    messages=[{
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {"type": "image_url", "image_url": {
                                "url": f"data:image/png;base64,{b64}"
                            }},
                        ],
                    }],
                    max_tokens=512,
                )
                kr.mark_ok("groq", key)
                return response.choices[0].message.content
            except groq_lib.RateLimitError as e:
                kr.mark_failed("groq", key, "rate limit")
                last_err = e
            except groq_lib.AuthenticationError as e:
                kr.mark_failed("groq", key, "auth error")
                last_err = e
            except Exception as e:
                last_err = e
                break
        raise last_err or RuntimeError("Groq vision failed")


class GeminiBackend(LLMBackend):
    @property
    def name(self):
        return "gemini"

    def chat(self, messages: list, tools: list = None, stream: bool = False) -> str:
        import google.generativeai as genai
        from google.api_core.exceptions import ResourceExhausted, PermissionDenied
        last_err = None
        for _ in range(kr._rotators["gemini"].total_count() or 1):
            key = kr.get("gemini")
            if not key:
                raise RuntimeError("All Gemini API keys exhausted")
            try:
                genai.configure(api_key=key)
                system_text = next((m["content"] for m in messages if m["role"] == "system"), "")
                history = [
                    {"role": "user" if m["role"] == "user" else "model", "parts": [m["content"]]}
                    for m in messages if m["role"] in ("user", "assistant")
                ]
                model = genai.GenerativeModel(
                    settings.GEMINI_MODEL,
                    system_instruction=system_text or None,
                )
                chat = model.start_chat(history=history[:-1] if history else [])
                last_msg = history[-1]["parts"][0] if history else ""
                response = chat.send_message(last_msg)
                kr.mark_ok("gemini", key)
                return response.text
            except ResourceExhausted as e:
                kr.mark_failed("gemini", key, "rate limit")
                last_err = e
            except PermissionDenied as e:
                kr.mark_failed("gemini", key, "auth error")
                last_err = e
            except Exception as e:
                last_err = e
                break
        raise last_err or RuntimeError("Gemini chat failed")

    def vision(self, image_path: str, prompt: str) -> str:
        import google.generativeai as genai
        import PIL.Image
        from google.api_core.exceptions import ResourceExhausted, PermissionDenied
        last_err = None
        for _ in range(kr._rotators["gemini"].total_count() or 1):
            key = kr.get("gemini")
            if not key:
                raise RuntimeError("All Gemini API keys exhausted")
            try:
                genai.configure(api_key=key)
                model = genai.GenerativeModel(settings.GEMINI_VISION_MODEL)
                img = PIL.Image.open(image_path)
                response = model.generate_content([prompt, img])
                kr.mark_ok("gemini", key)
                return response.text
            except ResourceExhausted as e:
                kr.mark_failed("gemini", key, "rate limit")
                last_err = e
            except PermissionDenied as e:
                kr.mark_failed("gemini", key, "auth error")
                last_err = e
            except Exception as e:
                last_err = e
                break
        raise last_err or RuntimeError("Gemini vision failed")


class OllamaBackend(LLMBackend):
    @property
    def name(self):
        return "ollama"

    def chat(self, messages: list, tools: list = None, stream: bool = False) -> str:
        import ollama as _ollama
        response = _ollama.chat(
            model=settings.OLLAMA_MODEL,
            messages=messages,
            stream=False,
        )
        return response["message"]["content"]

    def vision(self, image_path: str, prompt: str) -> str:
        import ollama as _ollama
        with open(image_path, "rb") as f:
            img_bytes = f.read()
        response = _ollama.chat(
            model="moondream",
            messages=[{
                "role": "user",
                "content": prompt,
                "images": [img_bytes],
            }],
        )
        return response["message"]["content"]


def _build_backend(name: str) -> LLMBackend | None:
    try:
        if name == "groq" and kr._rotators.get("groq", kr.KeyRotator("groq", [])).has_any():
            return GroqBackend()
        if name == "gemini" and kr._rotators.get("gemini", kr.KeyRotator("gemini", [])).has_any():
            return GeminiBackend()
        if name == "ollama":
            return OllamaBackend()
    except Exception as e:
        log.warning(f"Failed to init {name} backend: {e}")
    return None


class LLM:
    """Unified LLM interface with automatic key rotation and provider fallback."""

    def __init__(self):
        self._primary = _build_backend(settings.LLM_PRIMARY)
        self._fallback = _build_backend(settings.LLM_FALLBACK)
        if self._primary:
            log.info(f"LLM primary: {self._primary.name}")
        if self._fallback:
            log.info(f"LLM fallback: {self._fallback.name}")
        if not self._primary and not self._fallback:
            raise RuntimeError(
                "No LLM backend available. Add keys to config.toml"
            )

    def chat(self, messages: list, tools: list = None, stream: bool = False) -> str:
        backend = self._primary or self._fallback
        try:
            return backend.chat(messages, tools=tools, stream=stream)
        except Exception as e:
            log.warning(f"{backend.name} failed: {e}")
            if self._fallback and self._fallback is not backend:
                log.info(f"Falling back to {self._fallback.name}")
                return self._fallback.chat(messages, tools=tools, stream=stream)
            raise

    def vision(self, image_path: str, prompt: str) -> str:
        vision_backend = _build_backend(settings.LLM_VISION_MODEL) or self._primary or self._fallback
        try:
            return vision_backend.vision(image_path, prompt)
        except Exception as e:
            log.warning(f"Vision failed on {vision_backend.name}: {e}")
            if self._fallback and self._fallback is not vision_backend:
                return self._fallback.vision(image_path, prompt)
            raise


_llm_instance: LLM | None = None


def get_llm() -> LLM:
    global _llm_instance
    if _llm_instance is None:
        _llm_instance = LLM()
    return _llm_instance
