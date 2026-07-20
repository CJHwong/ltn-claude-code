"""Tests for the Claude Code CLI LLM client.

Library mocking (subprocess) happens here at the adapter boundary, which is
where it belongs -- the client's whole job is to shell out to ``claude``.
"""

from __future__ import annotations

import asyncio
import json
from unittest.mock import patch

import pytest

from ltn_claude_code.client import ClaudeCodeConfig, ClaudeCodeLLMClient


class FakeProc:
    """Stand-in for an asyncio subprocess with a scripted result."""

    def __init__(self, returncode: int, stdout: bytes = b'', stderr: bytes = b'') -> None:
        self.returncode = returncode
        self._stdout = stdout
        self._stderr = stderr

    async def communicate(self, input: bytes | None = None) -> tuple[bytes, bytes]:  # noqa: A002 -- matches asyncio API
        return self._stdout, self._stderr


def _ok_payload(result: str = 'summary') -> bytes:
    return json.dumps({'result': result, 'usage': {'input_tokens': 3}, 'total_cost_usd': 0.01}).encode()


def test_first_call_creates_session_then_resumes():
    client = ClaudeCodeLLMClient(ClaudeCodeConfig(session_id='fixed-id'))
    captured: list[list[str]] = []

    async def fake_exec(*cmd, **_kwargs):
        captured.append(list(cmd))
        return FakeProc(0, _ok_payload())

    async def scenario():
        await client.chat_single('m', 'hi')
        await client.chat_single('m', 'again')

    with patch('asyncio.create_subprocess_exec', side_effect=fake_exec):
        asyncio.run(scenario())

    assert '--session-id' in captured[0] and '--resume' not in captured[0]
    assert '--resume' in captured[1] and '--session-id' not in captured[1]


def test_failed_create_still_resumes_instead_of_reusing_session_id():
    """Regression: a first call that fails after claude registers the session
    must not retry with the same --session-id (that yields 'already in use')."""
    client = ClaudeCodeLLMClient(ClaudeCodeConfig(session_id='fixed-id'))
    captured: list[list[str]] = []

    async def fake_exec(*cmd, **_kwargs):
        captured.append(list(cmd))
        # Mimic Gary's 401: claude runs (creating the session) then fails.
        return FakeProc(1, b'', b'API Error: 401 Invalid authentication credentials')

    async def scenario():
        with pytest.raises(RuntimeError, match='401'):
            await client.chat_single('m', 'first')
        with pytest.raises(RuntimeError, match='401'):
            await client.chat_single('m', 'second')

    with patch('asyncio.create_subprocess_exec', side_effect=fake_exec):
        asyncio.run(scenario())

    assert '--session-id' in captured[0]
    # The retry must resume, not collide on the same fresh session id.
    assert '--resume' in captured[1] and '--session-id' not in captured[1]


def test_check_connectivity_reports_missing_binary():
    client = ClaudeCodeLLMClient()
    with patch('shutil.which', return_value=None):
        ok, msg = client.check_connectivity()
    assert not ok and 'PATH' in msg


def test_check_connectivity_reports_logged_out():
    client = ClaudeCodeLLMClient()
    completed = type('R', (), {'stdout': json.dumps({'loggedIn': False}), 'stderr': ''})()
    with patch('shutil.which', return_value='/usr/bin/claude'), patch('subprocess.run', return_value=completed):
        ok, msg = client.check_connectivity()
    assert not ok and 'claude auth login' in msg


def test_check_connectivity_passes_when_logged_in():
    client = ClaudeCodeLLMClient()
    completed = type('R', (), {'stdout': json.dumps({'loggedIn': True, 'email': 'x@y.z'}), 'stderr': ''})()
    with patch('shutil.which', return_value='/usr/bin/claude'), patch('subprocess.run', return_value=completed):
        ok, msg = client.check_connectivity()
    assert ok and not msg
