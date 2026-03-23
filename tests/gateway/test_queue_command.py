import pytest
from unittest.mock import AsyncMock, MagicMock

from gateway.config import GatewayConfig, Platform, PlatformConfig
from gateway.platforms.base import BasePlatformAdapter, MessageEvent, SendResult
from gateway.run import GatewayRunner
from gateway.session import SessionSource, build_session_key


class _QueueAdapter(BasePlatformAdapter):
    def __init__(self):
        super().__init__(PlatformConfig(enabled=True, token="***"), Platform.TELEGRAM)

    async def connect(self):
        return True

    async def disconnect(self):
        pass

    async def send(self, chat_id, content, reply_to=None, metadata=None):
        return SendResult(success=True, message_id="1")

    async def send_typing(self, chat_id, metadata=None):
        pass

    async def get_chat_info(self, chat_id):
        return {"id": chat_id}


def _make_runner():
    runner = object.__new__(GatewayRunner)
    runner.config = GatewayConfig(
        platforms={Platform.TELEGRAM: PlatformConfig(enabled=True, token="***")}
    )
    runner.adapters = {Platform.TELEGRAM: _QueueAdapter()}
    runner._running_agents = {}
    runner._pending_messages = {}
    runner._pending_approvals = {}
    runner._voice_mode = {}
    runner._is_user_authorized = lambda _source: True
    runner._handle_reset_command = AsyncMock(return_value="reset")
    runner.hooks = MagicMock()
    runner.hooks.emit = AsyncMock()
    return runner


def _make_event(text: str, chat_id: str = "12345") -> MessageEvent:
    source = SessionSource(
        platform=Platform.TELEGRAM,
        chat_id=chat_id,
        chat_type="dm",
    )
    return MessageEvent(text=text, source=source, message_id="1")


@pytest.mark.asyncio
async def test_queue_command_preserves_multiple_pending_prompts():
    runner = _make_runner()
    event1 = _make_event("/queue first")
    event2 = _make_event("/queue second")
    session_key = build_session_key(event1.source)
    runner._running_agents[session_key] = MagicMock()

    assert await runner._handle_message(event1) == "Queued for the next turn."
    assert await runner._handle_message(event2) == "Queued for the next turn."

    adapter = runner.adapters[Platform.TELEGRAM]
    first = adapter.get_pending_message(session_key)
    second = adapter.get_pending_message(session_key)

    assert first is not None
    assert first.text == "first"
    assert second is not None
    assert second.text == "second"
    assert adapter.get_pending_message(session_key) is None


@pytest.mark.asyncio
async def test_new_command_clears_all_queued_prompts():
    runner = _make_runner()
    queued = _make_event("/queue first")
    session_key = build_session_key(queued.source)
    runner._running_agents[session_key] = MagicMock()

    await runner._handle_message(queued)
    await runner._handle_message(_make_event("/queue second"))

    result = await runner._handle_message(_make_event("/new"))

    assert result == "reset"
    runner._handle_reset_command.assert_awaited_once()
    adapter = runner.adapters[Platform.TELEGRAM]
    assert adapter.get_pending_message(session_key) is None
