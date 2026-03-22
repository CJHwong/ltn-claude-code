"""Claude Code CLI LLM client -- implements the LLMClient protocol via subprocess."""

from __future__ import annotations

import asyncio
import json
import logging
import shutil
import tempfile
import uuid
from dataclasses import dataclass, field

from lazy_take_notes.plugin_api import ChatMessage, ChatResponse, InfraConfig

logger = logging.getLogger('ltn.claude_code')


def _extract_prompt(messages: list[ChatMessage]) -> tuple[str | None, str]:
    """Extract system prompt and last user prompt from a message list.

    Returns (system_prompt, user_prompt). The system message (if any) is
    passed via --append-system-prompt so Claude Code treats it as instructions.
    Only the last user message is sent as the prompt since session
    persistence handles history.
    """
    system_prompt = None
    user_prompt = ''

    for msg in messages:
        if msg.role == 'system':
            system_prompt = msg.content
        elif msg.role == 'user':
            user_prompt = msg.content

    if not user_prompt:
        parts = [msg.content for msg in messages if msg.role != 'system']
        user_prompt = '\n\n'.join(parts)

    return system_prompt, user_prompt


@dataclass
class ClaudeCodeConfig:
    """Configuration for the Claude Code subprocess."""

    digest_model: str = 'sonnet'
    interactive_model: str = 'haiku'
    max_budget_usd: float = 1.0
    cwd: str | None = None
    session_id: str = field(default_factory=lambda: str(uuid.uuid4()))


class ClaudeCodeLLMClient:
    """LLMClient implementation that shells out to the ``claude`` CLI.

    Maintains a persistent session via ``--session-id`` so that conversation
    history accumulates across digest cycles and queries. The session ID is
    generated once at construction and reused for all subsequent calls.

    An asyncio lock serializes calls to prevent "session already in use"
    errors when digest and query fire concurrently.
    """

    def __init__(self, config: ClaudeCodeConfig | None = None) -> None:
        self._config = config or ClaudeCodeConfig()
        self._lock = asyncio.Lock()
        self._session_created = False
        # Default cwd to temp dir to avoid CLAUDE.md contamination.
        if self._config.cwd is None:
            self._config.cwd = tempfile.gettempdir()

    async def chat(self, model: str, messages: list[ChatMessage]) -> ChatResponse:
        """Send a multi-turn conversation to Claude Code CLI.

        Used by digest use case. Always uses digest_model since the config
        model name (e.g. 'gpt-oss:20b') is meaningless to Claude Code.
        """
        system_prompt, user_prompt = _extract_prompt(messages)
        return await self._run(
            self._config.digest_model,
            user_prompt,
            system_prompt=system_prompt,
        )

    async def chat_single(self, model: str, prompt: str) -> str:
        """Single-turn convenience -- returns raw text.

        Used by quick action / query use case. Uses interactive_model.
        """
        response = await self._run(self._config.interactive_model, prompt)
        return response.content

    def check_connectivity(self) -> tuple[bool, str]:
        """Check that the ``claude`` binary is on PATH."""
        if shutil.which('claude') is None:
            return False, 'claude CLI not found on PATH'
        return True, ''

    def check_models(self, models: list[str]) -> list[str]:
        """Always returns empty -- Claude Code handles model selection."""
        return []

    async def _run(
        self,
        model: str,
        prompt: str,
        *,
        system_prompt: str | None = None,
    ) -> ChatResponse:
        """Execute ``claude --print`` with session persistence.

        Serialized via asyncio lock to avoid session-in-use conflicts.
        """
        cmd = [
            'claude',
            '--print',
            '--output-format', 'json',
            '--model', model,
            '--max-budget-usd', str(self._config.max_budget_usd),
            '--tools', '',
        ]
        # First call: --session-id to create. Subsequent: --resume to continue.
        if self._session_created:
            cmd.extend(['--resume', self._config.session_id])
        else:
            cmd.extend(['--session-id', self._config.session_id])
        if system_prompt:
            cmd.extend(['--append-system-prompt', system_prompt])

        logger.debug('claude cmd: %s (cwd=%s)', ' '.join(cmd), self._config.cwd)

        async with self._lock:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=self._config.cwd,
            )
            stdout, stderr = await proc.communicate(input=prompt.encode())

        raw_out = stdout.decode()

        if proc.returncode != 0:
            error_detail = stderr.decode().strip()
            if not error_detail and raw_out:
                try:
                    err_data = json.loads(raw_out)
                    error_detail = err_data.get('result', '')
                except json.JSONDecodeError:
                    error_detail = raw_out[:200]
            raise RuntimeError(f'claude CLI failed: {error_detail or f"exit code {proc.returncode}"}')

        data = json.loads(raw_out)

        if data.get('is_error'):
            raise RuntimeError(f'claude CLI error: {data.get("result", "unknown")}')

        self._session_created = True
        usage = data.get('usage', {})
        cost = data.get('total_cost_usd', 0)
        logger.debug(
            'claude response: %d chars, %d input tokens, $%.4f',
            len(data.get('result', '')),
            usage.get('input_tokens', 0),
            cost,
        )
        return ChatResponse(
            content=data.get('result', ''),
            prompt_tokens=usage.get('input_tokens', 0),
        )


def create_llm_client(infra: InfraConfig) -> ClaudeCodeLLMClient:
    """Factory for the ``lazy_take_notes.llm_providers`` entry point.

    Reads plugin-specific config from ``infra.model_extra['claude_code']``.

    Example config.yaml::

        llm_provider: claude-code
        claude_code:
          digest_model: sonnet
          interactive_model: haiku
          budget: 1.0
    """
    extra = (infra.model_extra or {}).get('claude_code', {})
    config = ClaudeCodeConfig(
        digest_model=extra.get('digest_model', 'sonnet'),
        interactive_model=extra.get('interactive_model', 'haiku'),
        max_budget_usd=extra.get('budget', 1.0),
        cwd=extra.get('cwd'),
    )
    return ClaudeCodeLLMClient(config)


create_llm_client.manages_models = True  # type: ignore[attr-defined]
