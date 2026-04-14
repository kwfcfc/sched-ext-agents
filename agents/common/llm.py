"""
LLM client wrapper for all agents.

Centralizes API configuration, retry logic, and conversation management.
Each agent calls llm.complete() with its own system prompt and messages.
"""

from __future__ import annotations
import os
import time
import logging
from dataclasses import dataclass, field
from pathlib import Path

import anthropic

log = logging.getLogger(__name__)

# Maximum tokens per response
DEFAULT_MAX_TOKENS = 8192


@dataclass
class Message:
    role: str       # "user" | "assistant"
    content: str


@dataclass
class Conversation:
    """Maintains conversation history for a single agent session."""
    system_prompt: str
    messages: list[Message] = field(default_factory=list)
    knowledge_context: str = ""  # Injected domain knowledge

    def add_user(self, content: str):
        self.messages.append(Message(role="user", content=content))

    def add_assistant(self, content: str):
        self.messages.append(Message(role="assistant", content=content))

    def to_api_messages(self) -> list[dict]:
        msgs = []
        # Inject knowledge context as the first user message if present
        if self.knowledge_context and len(self.messages) <= 1:
            msgs.append({
                "role": "user",
                "content": (
                    f"<domain_knowledge>\n{self.knowledge_context}\n</domain_knowledge>\n\n"
                    + (self.messages[0].content if self.messages else "")
                ),
            })
            start = 1
        else:
            start = 0

        for msg in self.messages[start:]:
            msgs.append({"role": msg.role, "content": msg.content})
        return msgs


class LLMClient:
    """Thin wrapper around the Anthropic API with retry and logging."""

    def __init__(
        self,
        model: str | None = None,
        max_tokens: int = DEFAULT_MAX_TOKENS,
    ):
        self.client = anthropic.Anthropic(
            api_key=os.environ.get("ANTHROPIC_API_KEY"),
        )
        self.model = model or os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-20250514")
        self.max_tokens = max_tokens
        self._total_input_tokens = 0
        self._total_output_tokens = 0

    def complete(
        self,
        conversation: Conversation,
        temperature: float = 0.0,
        stop_sequences: list[str] | None = None,
    ) -> str:
        """Send a conversation to the API and return the assistant's response."""
        messages = conversation.to_api_messages()

        for attempt in range(3):
            try:
                response = self.client.messages.create(
                    model=self.model,
                    max_tokens=self.max_tokens,
                    system=conversation.system_prompt,
                    messages=messages,
                    temperature=temperature,
                    stop_sequences=stop_sequences or [],
                )

                # Track usage
                self._total_input_tokens += response.usage.input_tokens
                self._total_output_tokens += response.usage.output_tokens

                text = response.content[0].text
                conversation.add_assistant(text)

                log.debug(
                    "LLM response: %d input tokens, %d output tokens",
                    response.usage.input_tokens,
                    response.usage.output_tokens,
                )
                return text

            except anthropic.RateLimitError:
                wait = 2 ** attempt * 5
                log.warning("Rate limited, waiting %ds (attempt %d/3)", wait, attempt + 1)
                time.sleep(wait)
            except anthropic.APIError as e:
                log.error("API error: %s", e)
                if attempt == 2:
                    raise
                time.sleep(2)

        raise RuntimeError("LLM call failed after 3 attempts")

    def load_system_prompt(self, path: str, **kwargs) -> str:
        """Load a system prompt from a markdown file, with optional variable substitution."""
        content = Path(path).read_text()
        for key, val in kwargs.items():
            content = content.replace(f"{{{{{key}}}}}", str(val))
        return content

    @property
    def usage_summary(self) -> dict:
        return {
            "total_input_tokens": self._total_input_tokens,
            "total_output_tokens": self._total_output_tokens,
        }
