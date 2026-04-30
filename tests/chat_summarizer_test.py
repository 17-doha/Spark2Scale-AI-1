"""
Chat Summarizer Route — Integrated Test Suite
=============================================
Unit tests for the chat-summarizer endpoint
(`app/api/routes/chat_summarizer.py`).

The summarizer takes a list of chat messages between a founder and the
document-chat assistant and returns a structured `document_changes` list
that downstream agents (BMC enhance, etc.) consume.

Sections:
  1. SCHEMA VALIDATION
  2. HAPPY PATHS (clean JSON, fenced JSON, missing key)
  3. ERROR PATHS (empty messages, JSON decode, LLM exception)
"""

import json
import pytest
from unittest.mock import patch, MagicMock

from fastapi import HTTPException

from app.api.routes.chat_summarizer import summarize_chat
from app.graph.document_chat.schema import (
    ChatMessageInput,
    ChatSummarizerRequest,
    ChatSummarizerResponse,
)


def _make_request(messages):
    """Helper: builds a ChatSummarizerRequest from a list of (role, content) tuples."""
    return ChatSummarizerRequest(
        messages=[ChatMessageInput(role=r, content=c) for r, c in messages]
    )


# ===========================================================================
# 1. SCHEMA VALIDATION
# ===========================================================================
class TestChatSummarizerSchemas:
    def test_chat_message_input_round_trip(self):
        msg = ChatMessageInput(role="user", content="add el-sewedy")
        assert msg.role == "user"
        assert msg.content == "add el-sewedy"

    def test_request_round_trip(self):
        req = _make_request([("user", "hello"), ("assistant", "hi")])
        assert len(req.messages) == 2
        assert req.messages[0].role == "user"
        assert req.messages[1].content == "hi"

    def test_response_round_trip(self):
        resp = ChatSummarizerResponse(
            summary={
                "document_changes": ["Add El-Sewedy as a key partnership"],
                "enhanced_at": "2026-04-30T12:00:00+00:00",
            }
        )
        assert resp.summary["document_changes"] == [
            "Add El-Sewedy as a key partnership"
        ]


# ===========================================================================
# 2. HAPPY PATHS
# ===========================================================================
class TestChatSummarizerHappyPaths:
    @pytest.mark.asyncio
    @patch("app.api.routes.chat_summarizer.get_llm")
    async def test_summarize_returns_document_changes(self, mock_get_llm):
        """LLM returns clean JSON; route returns the parsed change list."""
        fake_response = MagicMock()
        fake_response.content = json.dumps({
            "document_changes": [
                "Add El-Sewedy as a key partnership",
                "Tighten value proposition wording",
            ]
        })
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = fake_response
        mock_get_llm.return_value = mock_llm

        req = _make_request([
            ("user", "please add El-Sewedy as a partner"),
            ("assistant", "noted"),
            ("user", "and tighten the value prop"),
        ])
        result = await summarize_chat(req)

        assert isinstance(result, ChatSummarizerResponse)
        assert result.summary["document_changes"] == [
            "Add El-Sewedy as a key partnership",
            "Tighten value proposition wording",
        ]
        assert "enhanced_at" in result.summary
        mock_llm.invoke.assert_called_once()

    @pytest.mark.asyncio
    @patch("app.api.routes.chat_summarizer.get_llm")
    async def test_summarize_strips_markdown_json_fence(self, mock_get_llm):
        """LLM-returned JSON wrapped in ```json fences is still parsed."""
        fake_response = MagicMock()
        fake_response.content = (
            "```json\n"
            '{"document_changes": ["Add competitor analysis"]}\n'
            "```"
        )
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = fake_response
        mock_get_llm.return_value = mock_llm

        result = await summarize_chat(_make_request([("user", "compare us to rivals")]))
        assert result.summary["document_changes"] == ["Add competitor analysis"]

    @pytest.mark.asyncio
    @patch("app.api.routes.chat_summarizer.get_llm")
    async def test_summarize_strips_plain_code_fence(self, mock_get_llm):
        """A plain ``` fence (no language tag) is also stripped."""
        fake_response = MagicMock()
        fake_response.content = (
            "```\n"
            '{"document_changes": []}\n'
            "```"
        )
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = fake_response
        mock_get_llm.return_value = mock_llm

        result = await summarize_chat(_make_request([("user", "just chitchat")]))
        assert result.summary["document_changes"] == []

    @pytest.mark.asyncio
    @patch("app.api.routes.chat_summarizer.get_llm")
    async def test_summarize_handles_missing_key(self, mock_get_llm):
        """If the LLM omits document_changes, the route defaults it to []."""
        fake_response = MagicMock()
        fake_response.content = '{"other_field": "noise"}'
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = fake_response
        mock_get_llm.return_value = mock_llm

        result = await summarize_chat(_make_request([("user", "hi")]))
        assert result.summary["document_changes"] == []

    @pytest.mark.asyncio
    @patch("app.api.routes.chat_summarizer.get_llm")
    async def test_summarize_uses_groq_provider(self, mock_get_llm):
        """Regression: route must request Groq, not Gemini (free-tier 429s)."""
        fake_response = MagicMock()
        fake_response.content = '{"document_changes": []}'
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = fake_response
        mock_get_llm.return_value = mock_llm

        await summarize_chat(_make_request([("user", "hi")]))

        kwargs = mock_get_llm.call_args.kwargs
        assert kwargs.get("provider") == "groq"

    @pytest.mark.asyncio
    @patch("app.api.routes.chat_summarizer.get_llm")
    async def test_summarize_concatenates_role_and_content(self, mock_get_llm):
        """The prompt sent to the LLM contains both the user and assistant turns."""
        fake_response = MagicMock()
        fake_response.content = '{"document_changes": []}'
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = fake_response
        mock_get_llm.return_value = mock_llm

        await summarize_chat(_make_request([
            ("user", "add a competitor"),
            ("assistant", "which one?"),
            ("user", "el-sewedy"),
        ]))

        # The route builds a single HumanMessage with the conversation appended.
        call_args, _ = mock_llm.invoke.call_args
        human_msg = call_args[0][0]
        text = human_msg.content
        assert "USER: add a competitor" in text
        assert "ASSISTANT: which one?" in text
        assert "USER: el-sewedy" in text


# ===========================================================================
# 3. ERROR PATHS
# ===========================================================================
class TestChatSummarizerErrorPaths:
    @pytest.mark.asyncio
    async def test_empty_messages_returns_400(self):
        """Empty messages list short-circuits to 400 before any LLM call."""
        req = ChatSummarizerRequest(messages=[])
        with pytest.raises(HTTPException) as exc:
            await summarize_chat(req)
        assert exc.value.status_code == 400
        assert "No messages" in exc.value.detail

    @pytest.mark.asyncio
    @patch("app.api.routes.chat_summarizer.get_llm")
    async def test_unparseable_json_returns_500(self, mock_get_llm):
        """LLM returns gibberish — route raises 500 with a friendly detail."""
        fake_response = MagicMock()
        fake_response.content = "not json at all, just prose"
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = fake_response
        mock_get_llm.return_value = mock_llm

        with pytest.raises(HTTPException) as exc:
            await summarize_chat(_make_request([("user", "hi")]))
        assert exc.value.status_code == 500
        assert "unparseable" in exc.value.detail.lower()

    @pytest.mark.asyncio
    @patch("app.api.routes.chat_summarizer.get_llm")
    async def test_llm_exception_returns_500(self, mock_get_llm):
        """LLM raises (e.g. 429 RESOURCE_EXHAUSTED) — route surfaces a 500."""
        mock_llm = MagicMock()
        mock_llm.invoke.side_effect = RuntimeError("rate limited")
        mock_get_llm.return_value = mock_llm

        with pytest.raises(HTTPException) as exc:
            await summarize_chat(_make_request([("user", "hi")]))
        assert exc.value.status_code == 500
        assert "Summarization failed" in exc.value.detail
        assert "rate limited" in exc.value.detail
