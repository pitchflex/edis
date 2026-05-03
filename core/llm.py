# Pluggable LLM backend — Groq (primary), Gemini (fallback), Ollama (offline)

import base64
import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Generator

import settings

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
    def __init__(self):
        from groq import Groq
        self._client = Groq(api_key=settings.GROQ_API_KEY)

    @property
    def name(self):
        return "groq"

    def chat(self, messages: list, tools: list = None, stream: bool = False) -> str:
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
            return self._stream(kwargs)

        response = self._client.chat.completions.create(**kwargs)
        return self._parse(response)

    def _stream(self, kwargs) -> Generator:
        for chunk in self._client.chat.completions.create(**kwargs):
            delta = chunk.choices[0].delta
            if delta.content:
                yield delta.content

    def _parse(self, response):
        msg = response.choices[0].message
        # return tool calls if present, else text
        if msg.tool_calls:
            return msg
        return msg.content or ""

    def vision(self, image_path: str, prompt: str) -> str:
        with open(image_path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode()
        response = self._client.chat.completions.create(
            model=settings.GROQ_VISION_MODEL,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
                ],
            }],
            max_tokens=512,
        )
        return response.choices[0].message.content


class GeminiBackend(LLMBackend):
    def __init__(self):
        import google.generativeai as genai
        genai.configure(api_key=settings.GEMINI_API_KEY)
        self._genai = genai
        self._model = genai.GenerativeModel(settings.GEMINI_MODEL)
        self._vision_model = genai.GenerativeModel(settings.GEMINI_VISION_MODEL)

    @property
    def name(self):
        return "gemini"

    def chat(self, messages: list, tools: list = None, stream: bool = False) -> str:
        # convert OpenAI-style messages to Gemini format
        history = []
        system_text = ""
        for m in messages:
            if m["role"] == "system":
                system_text = m["content"]
            elif m["role"] == "user":
                history.append({"role": "user", "parts": [m["content"]]})
            elif m["role"] == "assistant":
                history.append({"role": "model", "parts": [m["content"]]})

        model = self._genai.GenerativeModel(
            settings.GEMINI_MODEL,
            system_instruction=system_text if system_text else None,
        )
        chat = model.start_chat(history=history[:-1] if history else [])
        last = history[-1]["parts"][0] if history else ""
        response = chat.send_message(last)
        return response.text

    def vision(self, image_path: str, prompt: str) -> str:
        import PIL.Image
        img = PIL.Image.open(image_path)
        response = self._vision_model.generate_content([prompt, img])
        return response.text


class OllamaBackend(LLMBackend):
    def __init__(self):
        import ollama as _ollama
        self._ollama = _ollama

    @property
    def name(self):
        return "ollama"

    def chat(self, messages: list, tools: list = None, stream: bool = False) -> str:
        response = self._ollama.chat(
            model=settings.OLLAMA_MODEL,
            messages=messages,
            stream=False,
        )
        return response["message"]["content"]

    def vision(self, image_path: str, prompt: str) -> str:
        with open(image_path, "rb") as f:
            img_bytes = f.read()
        response = self._ollama.chat(
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
        if name == "groq" and settings.GROQ_API_KEY:
            return GroqBackend()
        if name == "gemini" and settings.GEMINI_API_KEY:
            return GeminiBackend()
        if name == "ollama":
            return OllamaBackend()
    except Exception as e:
        log.warning(f"Failed to init {name} backend: {e}")
    return None


class LLM:
    """Unified LLM interface with automatic fallback."""

    def __init__(self):
        self._primary = _build_backend(settings.LLM_PRIMARY)
        self._fallback = _build_backend(settings.LLM_FALLBACK)
        if self._primary:
            log.info(f"LLM primary: {self._primary.name}")
        if self._fallback:
            log.info(f"LLM fallback: {self._fallback.name}")
        if not self._primary and not self._fallback:
            raise RuntimeError("No LLM backend available. Set groq_key or gemini_key in config.toml")

    def chat(self, messages: list, tools: list = None, stream: bool = False) -> str:
        backend = self._primary or self._fallback
        try:
            return backend.chat(messages, tools=tools, stream=stream)
        except Exception as e:
            log.warning(f"{backend.name} failed: {e}, trying fallback")
            if self._fallback and self._fallback is not backend:
                return self._fallback.chat(messages, tools=tools, stream=stream)
            raise

    def vision(self, image_path: str, prompt: str) -> str:
        # prefer the configured vision backend
        vision_name = settings.LLM_VISION_MODEL
        backend = _build_backend(vision_name) or self._primary or self._fallback
        try:
            return backend.vision(image_path, prompt)
        except Exception as e:
            log.warning(f"Vision failed on {backend.name}: {e}")
            if self._fallback and self._fallback is not backend:
                return self._fallback.vision(image_path, prompt)
            raise


_llm_instance: LLM | None = None


def get_llm() -> LLM:
    global _llm_instance
    if _llm_instance is None:
        _llm_instance = LLM()
    return _llm_instance
