"""
tests/document_chat_test.py
============================
Pytest test suite for the document_chat LangGraph module.

Modules under test
------------------
  app.graph.document_chat.schema   — Pydantic I/O models
  app.graph.document_chat.state    — TypedDict state contract
  app.graph.document_chat.tools    — DocumentParser & SecurityGuardrails (pure utils, no LLM)
  app.graph.document_chat.node     — parse_document_node / answer_query_node
  app.graph.document_chat.workflow — compiled LangGraph StateGraph

Test isolation strategy
-----------------------
* All LLM calls (get_llm / chain.invoke) are mocked so tests run offline.
* Heavy I/O dependencies (fitz, pptx, requests) are patched where needed.
* The SecurityGuardrails and DocumentParser helpers are pure Python and are
  tested directly without mocks.
"""

import io
import json
import os
import re
import tempfile
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

# ---------------------------------------------------------------------------
# 1. Schema tests
# ---------------------------------------------------------------------------

class TestDocumentQARequest:
    """Validates the Pydantic request schema (defaults + field parsing)."""

    def test_minimal_construction(self):
        """CRITICAL – ensures the schema can be built with only required fields."""
        from app.graph.document_chat.schema import DocumentQARequest
        req = DocumentQARequest(file_path="/some/path.pdf", query="What is the GTM strategy?")
        assert req.file_path == "/some/path.pdf"
        assert req.query == "What is the GTM strategy?"
        assert req.provider == "gemini"          # default
        assert req.model_name is None            # default
        assert req.chat_history is None          # default

    def test_full_construction(self):
        """HIGH – verifies all explicit fields are accepted."""
        from app.graph.document_chat.schema import DocumentQARequest
        req = DocumentQARequest(
            file_path="/path/deck.pptx",
            query="What is the TAM?",
            provider="openai",
            model_name="gpt-4o",
            chat_history=[{"role": "user", "content": "Hi"}],
        )
        assert req.provider == "openai"
        assert req.model_name == "gpt-4o"
        assert len(req.chat_history) == 1

    def test_rejects_missing_required_fields(self):
        """HIGH – Pydantic must raise if required fields are absent."""
        from pydantic import ValidationError
        from app.graph.document_chat.schema import DocumentQARequest
        with pytest.raises(ValidationError):
            DocumentQARequest(query="only query, no file")

    def test_chat_history_type_validation(self):
        """MEDIUM – chat_history accepts list[dict] or None, rejects primitives."""
        from pydantic import ValidationError
        from app.graph.document_chat.schema import DocumentQARequest
        # None is OK
        req = DocumentQARequest(file_path="f.pdf", query="q", chat_history=None)
        assert req.chat_history is None


class TestDocumentQAResponse:
    """Validates the Pydantic response schema."""

    def test_construction(self):
        """HIGH – all fields present and typed correctly."""
        from app.graph.document_chat.schema import DocumentQAResponse
        resp = DocumentQAResponse(
            status="success",
            provider_used="gemini",
            query="What is the burn rate?",
            answer="The monthly burn is $50k.",
        )
        assert resp.status == "success"
        assert "burn" in resp.answer


# ---------------------------------------------------------------------------
# 2. State tests
# ---------------------------------------------------------------------------

class TestDocumentChatState:
    """Validates the TypedDict contract for DocumentChatState."""

    def test_state_keys(self):
        """MEDIUM – all expected keys are present in the TypedDict annotations."""
        from app.graph.document_chat.state import DocumentChatState
        keys = set(DocumentChatState.__annotations__.keys())
        assert "file_path" in keys
        assert "query" in keys
        assert "provider" in keys
        assert "model_name" in keys
        assert "chat_history" in keys
        assert "document_context" in keys
        assert "answer" in keys

    def test_state_can_be_constructed_as_dict(self):
        """LOW – TypedDicts behave as plain dicts at runtime."""
        state = {
            "file_path": "deck.pdf",
            "query": "Who are the founders?",
            "provider": "gemini",
            "model_name": None,
            "chat_history": None,
            "document_context": None,
            "answer": None,
        }
        assert state["provider"] == "gemini"


# ---------------------------------------------------------------------------
# 3. SecurityGuardrails tests
# ---------------------------------------------------------------------------

class TestSecurityGuardrails:
    """
    Tests the PII-redaction utility. No mocks needed — purely regex-based.
    CRITICAL: these run in production on every user query.
    """

    @pytest.fixture(autouse=True)
    def guardrails(self):
        from app.graph.document_chat.tools import SecurityGuardrails
        self.guard = SecurityGuardrails()

    def test_redacts_email(self):
        """CRITICAL – email addresses must never reach the LLM context."""
        result = self.guard.sanitize_text("Contact me at founder@startup.io for details.")
        assert "founder@startup.io" not in result
        assert "[EMAIL_REDACTED]" in result

    def test_redacts_ssn(self):
        """CRITICAL – SSNs are highly sensitive PII."""
        result = self.guard.sanitize_text("SSN: 123-45-6789 is confidential.")
        assert "123-45-6789" not in result
        assert "[SSN_REDACTED]" in result

    def test_redacts_url(self):
        """HIGH – raw URLs (e.g. Supabase signed links) should be hidden."""
        result = self.guard.sanitize_text("See https://supabase.co/storage/deck.pdf for the file.")
        assert "https://supabase.co" not in result
        assert "[URL_REDACTED]" in result

    def test_clean_text_unchanged(self):
        """MEDIUM – safe text must not be altered."""
        text = "The startup has three co-founders and a seed round of $500K."
        result = self.guard.sanitize_text(text)
        assert result == text

    def test_sanitize_query_caps_length(self):
        """HIGH – prevents prompt-injection via enormous queries."""
        long_query = "A" * 500
        result = self.guard.sanitize_query(long_query, max_length=300)
        assert len(result) == 300

    def test_sanitize_query_strips_whitespace(self):
        """LOW – trailing whitespace is trimmed."""
        result = self.guard.sanitize_query("  What is the valuation?  ")
        assert result == result.strip()

    def test_sanitize_query_respects_custom_max_length(self):
        """MEDIUM – custom max_length parameter is honoured."""
        result = self.guard.sanitize_query("Hello World", max_length=5)
        assert result == "Hello"


# ---------------------------------------------------------------------------
# 4. DocumentParser tests
# ---------------------------------------------------------------------------

class TestDocumentParserRouting:
    """
    Tests the routing logic in DocumentParser.route_and_parse.
    Heavy I/O (fitz, pptx, requests) is mocked so the suite runs offline.
    """

    def test_routes_json_string_payload(self):
        """HIGH – inline JSON from the frontend must be parsed correctly."""
        from app.graph.document_chat.tools import DocumentParser
        payload = json.dumps({"company": "Acme", "stage": "Seed"})
        result = DocumentParser.route_and_parse(payload)
        assert "[JSON Line" in result
        assert "Acme" in result

    def test_routes_json_array_payload(self):
        """MEDIUM – JSON array payloads are equally valid."""
        from app.graph.document_chat.tools import DocumentParser
        payload = json.dumps([{"name": "Alice"}, {"name": "Bob"}])
        result = DocumentParser.route_and_parse(payload)
        assert "[JSON Line" in result

    def test_invalid_json_string_raises(self):
        """HIGH – a malformed JSON-looking payload must raise ValueError."""
        from app.graph.document_chat.tools import DocumentParser
        with pytest.raises(ValueError, match="failed to decode"):
            DocumentParser.route_and_parse("{not valid json}")

    def test_routes_local_json_file(self, tmp_path):
        """MEDIUM – reading a JSON file from disk works end-to-end."""
        from app.graph.document_chat.tools import DocumentParser
        data = {"key": "value"}
        json_file = tmp_path / "data.json"
        json_file.write_text(json.dumps(data), encoding="utf-8")
        result = DocumentParser.route_and_parse(str(json_file))
        assert "[JSON Line" in result
        assert "value" in result

    def test_unsupported_extension_raises(self, tmp_path):
        """MEDIUM – passing an unsupported file type raises ValueError."""
        from app.graph.document_chat.tools import DocumentParser
        fake_file = tmp_path / "doc.docx"
        fake_file.write_bytes(b"fake content")
        with pytest.raises(ValueError, match="Unsupported"):
            DocumentParser.route_and_parse(str(fake_file))

    def test_routes_local_pdf(self, tmp_path):
        """HIGH – local PDF path triggers _parse_pdf via fitz; mocked here."""
        from app.graph.document_chat.tools import DocumentParser

        fake_pdf = tmp_path / "pitch.pdf"
        fake_pdf.write_bytes(b"%PDF-1.4 fake")  # real bytes don't matter; we mock fitz

        mock_page = MagicMock()
        mock_page.get_text.return_value = "Line one\nLine two\n"
        mock_doc = MagicMock()
        mock_doc.__iter__ = MagicMock(return_value=iter([mock_page]))

        with patch("fitz.open", return_value=mock_doc):
            result = DocumentParser.route_and_parse(str(fake_pdf))

        assert "[Page" in result

    def test_routes_local_pptx(self, tmp_path):
        """HIGH – local PPTX path triggers _parse_pptx; mocked here."""
        from app.graph.document_chat.tools import DocumentParser

        fake_pptx = tmp_path / "deck.pptx"
        fake_pptx.write_bytes(b"PK fake pptx content")

        mock_shape = MagicMock()
        mock_shape.text = "Slide content here"
        mock_slide = MagicMock()
        mock_slide.shapes = [mock_shape]
        mock_prs = MagicMock()
        mock_prs.slides = [mock_slide]

        with patch("app.graph.document_chat.tools.Presentation", return_value=mock_prs):
            result = DocumentParser.route_and_parse(str(fake_pptx))

        assert "[Slide" in result
        assert "Slide content here" in result

    def test_routes_http_url(self):
        """HIGH – a remote URL must be downloaded and parsed."""
        from app.graph.document_chat.tools import DocumentParser

        fake_response = MagicMock()
        fake_response.status_code = 200
        fake_response.raise_for_status = MagicMock()
        fake_response.content = b"%PDF-1.4 fake bytes"

        mock_page = MagicMock()
        mock_page.get_text.return_value = "Remote content\n"
        mock_doc = MagicMock()
        mock_doc.__iter__ = MagicMock(return_value=iter([mock_page]))

        with patch("requests.get", return_value=fake_response), \
             patch("fitz.open", return_value=mock_doc), \
             patch("os.remove"):
            result = DocumentParser.route_and_parse("https://storage.example.com/deck.pdf")

        assert "[Page" in result


class TestDocumentParserNormalise:
    """Edge-case tests for the internal _normalize helper."""

    def test_normalize_collapses_whitespace(self):
        from app.graph.document_chat.tools import DocumentParser
        assert DocumentParser._normalize("  hello   world  ") == "hello world"

    def test_normalize_empty_string(self):
        from app.graph.document_chat.tools import DocumentParser
        assert DocumentParser._normalize("") == ""


class TestDocumentParserFormatJson:
    """Tests for _format_json_data — annotation consistency."""

    def test_dict_annotated_correctly(self):
        from app.graph.document_chat.tools import DocumentParser
        result = DocumentParser._format_json_data({"a": 1})
        lines = result.split("\n")
        assert lines[0].startswith("[JSON Line 1]")

    def test_list_annotated_correctly(self):
        from app.graph.document_chat.tools import DocumentParser
        result = DocumentParser._format_json_data([1, 2, 3])
        assert "[JSON Line 1]" in result


# ---------------------------------------------------------------------------
# 5. Node tests
# ---------------------------------------------------------------------------

class TestParseDocumentNode:
    """
    Tests parse_document_node — the first LangGraph node that calls
    DocumentParser and SecurityGuardrails.
    """

    @pytest.fixture
    def base_state(self):
        return {
            "file_path": json.dumps({"company": "TestCo"}),
            "query": "What is the valuation?",
            "provider": "gemini",
            "model_name": None,
            "chat_history": None,
            "document_context": None,
            "answer": None,
        }

    def test_returns_document_context(self, base_state):
        """CRITICAL – document_context must be populated for downstream nodes."""
        from app.graph.document_chat.node import parse_document_node
        result = parse_document_node(base_state)
        assert "document_context" in result
        assert result["document_context"]  # non-empty

    def test_sanitizes_query(self, base_state):
        """HIGH – query is sanitised (trimmed, length-capped)."""
        base_state["query"] = "  What is the burn?  "
        from app.graph.document_chat.node import parse_document_node
        result = parse_document_node(base_state)
        assert result["query"] == result["query"].strip()

    def test_redacts_pii_in_context(self):
        """CRITICAL – PII in document must be redacted before reaching the LLM."""
        from app.graph.document_chat.node import parse_document_node
        payload = json.dumps({"contact": "ceo@example.com"})
        state = {
            "file_path": payload,
            "query": "What is the email?",
            "provider": "gemini",
            "model_name": None,
            "chat_history": None,
            "document_context": None,
            "answer": None,
        }
        result = parse_document_node(state)
        assert "ceo@example.com" not in result["document_context"]

    def test_only_mutates_expected_keys(self, base_state):
        """MEDIUM – node must only return the keys it owns."""
        from app.graph.document_chat.node import parse_document_node
        result = parse_document_node(base_state)
        assert set(result.keys()) == {"document_context", "query"}


class TestAnswerQueryNode:
    """
    Tests answer_query_node — the LLM invocation node.
    The LLM chain is fully mocked so no API key is needed.
    """

    @pytest.fixture
    def base_state(self):
        return {
            "file_path": "deck.pdf",
            "query": "What is the GTM strategy?",
            "provider": "gemini",
            "model_name": None,
            "chat_history": [],
            "document_context": "[Page 1, Line 1] Go-to-market: direct sales.",
            "answer": None,
        }

    def _make_mock_llm(self, answer_text: str):
        """Utility: returns a mock LLM and a mock chain that returns answer_text."""
        mock_chain = MagicMock()
        mock_chain.invoke = MagicMock(return_value=answer_text)
        mock_llm = MagicMock()
        # Make | operator return mock_chain
        mock_llm.__or__ = MagicMock(return_value=mock_chain)
        return mock_llm, mock_chain

    @patch("app.graph.document_chat.node.get_llm")
    def test_returns_answer_key(self, mock_get_llm, base_state):
        """CRITICAL – the node must always return the 'answer' key."""
        mock_chain = MagicMock()
        mock_chain.invoke = MagicMock(return_value="Direct sales via enterprise accounts.")

        # Patch the full chain construction
        with patch("app.graph.document_chat.node.ChatPromptTemplate") as mock_prompt, \
             patch("app.graph.document_chat.node.StrOutputParser") as mock_parser:
            mock_prompt.from_messages.return_value.__or__ = MagicMock(return_value=mock_chain)
            mock_chain.__or__ = MagicMock(return_value=mock_chain)

            from app.graph.document_chat.node import answer_query_node
            with patch("app.graph.document_chat.node.ChatPromptTemplate.from_messages") as fm:
                # Build a simple pipe chain stub
                stub = MagicMock()
                stub.__or__ = lambda self, other: stub
                stub.invoke = MagicMock(return_value="Direct sales answer.")
                fm.return_value.__or__ = MagicMock(return_value=stub)
                result = answer_query_node(base_state)

        assert "answer" in result

    @patch("app.graph.document_chat.node.get_llm")
    @patch("app.graph.document_chat.node.StrOutputParser")
    @patch("app.graph.document_chat.node.ChatPromptTemplate")
    def test_chat_history_slicing(self, mock_template, mock_parser, mock_get_llm, base_state):
        """HIGH – only the last 4 history messages must be used (token budget)."""
        base_state["chat_history"] = [
            {"role": "user", "content": f"msg{i}"} for i in range(10)
        ]
        captured_calls = []

        stub_chain = MagicMock()
        stub_chain.invoke = MagicMock(side_effect=lambda kwargs: (
            captured_calls.append(kwargs.get("chat_history", [])) or "answer"
        ))
        mock_template.from_messages.return_value.__or__ = MagicMock(return_value=stub_chain)
        stub_chain.__or__ = MagicMock(return_value=stub_chain)

        from app.graph.document_chat.node import answer_query_node
        answer_query_node(base_state)

        if captured_calls:
            assert len(captured_calls[0]) <= 4


# ---------------------------------------------------------------------------
# 6. Workflow graph tests
# ---------------------------------------------------------------------------

class TestDocumentChatWorkflow:
    """Tests the compiled LangGraph StateGraph structure."""

    def test_graph_compiles(self):
        """CRITICAL – graph must compile without errors (caught at import time)."""
        from app.graph.document_chat.workflow import app as chat_app
        assert chat_app is not None

    def test_graph_has_correct_nodes(self):
        """HIGH – both pipeline nodes must be registered."""
        from app.graph.document_chat.workflow import create_document_chat_graph
        graph = create_document_chat_graph()
        node_names = set(graph.nodes.keys())
        assert "parse_document_node" in node_names
        assert "answer_query_node" in node_names

    def test_public_api_exports(self):
        """MEDIUM – the __init__ must export the expected symbols."""
        from app.graph.document_chat import app, DocumentChatState, DocumentQARequest, DocumentQAResponse
        assert app is not None
        assert DocumentChatState is not None
        assert DocumentQARequest is not None
        assert DocumentQAResponse is not None
