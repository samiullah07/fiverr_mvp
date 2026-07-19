"""
LLM client abstraction for streaming chat completions.

Supports Claude, OpenAI, and OpenRouter (dev-only for testing) providers.
OpenRouter uses the OpenAI-compatible API endpoint.
"""
import os
from typing import Callable, Optional


SYSTEM_INSTRUCTIONS = (
    "You are a meeting copilot for a technical presenter. "
    "Answer concisely and professionally using ONLY the provided context. "
    "If the answer is NOT in the context, say so clearly, then optionally "
    "fall back to general knowledge. Always cite sources like [1], [2]."
)

GROUNDING_TEMPLATE = """Context documents (each from your own reference material):
{context}

Question: {question}

Instructions:
1. Answer primarily from the context above.
2. Cite sources inline like [1], [2] referring to the numbered context items.
3. If nothing relevant is found, respond: "I couldn't find this in your documents."
4. Keep answers concise and professional for a technical meeting setting.

Answer:"""


class LLMClient:
    """Minimal wrapper around Anthropic or OpenAI streaming chat."""

    def __init__(self, provider: str = "claude", model: Optional[str] = None):
        self.provider = provider.lower()
        if self.provider == "claude":
            try:
                import anthropic
            except ImportError:
                raise RuntimeError("pip install anthropic")
            self.client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
            self.model = model or os.getenv("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001")
        elif self.provider == "openai":
            try:
                import openai
            except ImportError:
                raise RuntimeError("pip install openai")
            self.client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
            self.model = model or "gpt-4o-mini"
        elif self.provider == "openrouter":
            # Development-only provider using OpenAI-compatible API
            try:
                import openai
            except ImportError:
                raise RuntimeError("pip install openai")
            self.client = openai.OpenAI(
                api_key=os.getenv("OPENROUTER_API_KEY"),
                base_url="https://openrouter.ai/api/v1"
            )
            self.model = model or os.getenv("OPENROUTER_MODEL", "meta-llama/llama-3.3-70b-instruct:free")
        else:
            raise ValueError(f"Unknown provider: {provider}")

    def stream_answer(self, prompt: str) -> str:
        """Stream the response, printing chunks to stdout, and return full text."""
        if self.provider == "claude":
            return self._stream_claude(prompt)
        return self._stream_openai(prompt)

    def complete(self, prompt: str, max_tokens: int = 100, system: Optional[str] = None) -> str:
        """Non-streaming call that returns the full response text.

        `system` is optional. Pass None (default) for lightweight tasks like
        question extraction where the grounding system prompt would be wrong.
        """
        try:
            if self.provider == "claude":
                kwargs = dict(
                    model=self.model,
                    max_tokens=max_tokens,
                    messages=[{"role": "user", "content": prompt}],
                )
                if system:
                    kwargs["system"] = system
                msg = self.client.messages.create(**kwargs)
                return msg.content[0].text
            else:  # openai / openrouter
                messages = []
                if system:
                    messages.append({"role": "system", "content": system})
                messages.append({"role": "user", "content": prompt})
                resp = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    max_tokens=max_tokens,
                    stream=False,
                )
                return resp.choices[0].message.content
        except Exception as e:
            return f"LLM Error: {e}"

    def stream_answer_callback(self, prompt: str, on_token: Callable[[str], None]) -> str:
        """Stream the response, calling on_token for each chunk, and return full text."""
        if self.provider == "claude":
            return self._stream_claude_callback(prompt, on_token)
        return self._stream_openai_callback(prompt, on_token)

    def _stream_claude_callback(self, prompt: str, on_token: Callable[[str], None]) -> str:
        import anthropic
        stream = self.client.messages.create(
            model=self.model,
            max_tokens=1024,
            system=SYSTEM_INSTRUCTIONS,
            messages=[{"role": "user", "content": prompt}],
            stream=True,
        )
        full = []
        for chunk in stream:
            if chunk.type == "content_block_delta":
                text = chunk.delta.text
                on_token(text)
                full.append(text)
        return "".join(full)

    def _stream_openai_callback(self, prompt: str, on_token: Callable[[str], None]) -> str:
        import openai
        stream = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": SYSTEM_INSTRUCTIONS},
                {"role": "user", "content": prompt},
            ],
            stream=True,
            max_tokens=1024,
        )
        full = []
        for chunk in stream:
            delta = chunk.choices[0].delta.content
            if delta:
                on_token(delta)
                full.append(delta)
        return "".join(full)

    def _stream_claude(self, prompt: str) -> str:
        import anthropic
        stream = self.client.messages.create(
            model=self.model,
            max_tokens=1024,
            system=SYSTEM_INSTRUCTIONS,
            messages=[{"role": "user", "content": prompt}],
            stream=True,
        )
        full = []
        for chunk in stream:
            if chunk.type == "content_block_delta":
                text = chunk.delta.text
                print(text, end="", flush=True)
                full.append(text)
        print()
        return "".join(full)

    def _stream_openai(self, prompt: str) -> str:
        import openai
        stream = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": SYSTEM_INSTRUCTIONS},
                {"role": "user", "content": prompt},
            ],
            stream=True,
            max_tokens=1024,
        )
        full = []
        for chunk in stream:
            delta = chunk.choices[0].delta.content
            if delta:
                print(delta, end="", flush=True)
                full.append(delta)
        print()
        return "".join(full)