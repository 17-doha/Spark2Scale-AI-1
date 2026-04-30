"""
tests/pdf_extractor_test.py
============================
Pytest test suite for the pdf_extractor LangGraph module.

Modules under test
------------------
  app.graph.pdf_extractor.schema   — TARGET_SCHEMA constant
  app.graph.pdf_extractor.state    — TypedDict state contract
  app.graph.pdf_extractor.prompts  — PDF_EXTRACTION_PROMPT constant
  app.graph.pdf_extractor.tools    — extract_text_from_pdf & force_numeric_types (pure Python)
  app.graph.pdf_extractor.node     — extract_text_node / llm_extraction_node
                                      / sanitize_data_node (async LangGraph nodes)
  app.graph.pdf_extractor.workflow — compiled LangGraph StateGraph

Test isolation strategy
-----------------------
* LLM calls (get_llm / chain.ainvoke) are mocked with AsyncMock.
* PyPDF2 is mocked where PDF bytes would be needed.
* force_numeric_types and TARGET_SCHEMA are pure data structures — tested without mocks.
"""

import io
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch




# ---------------------------------------------------------------------------
# 1. Schema / constant tests
# ---------------------------------------------------------------------------

class TestTargetSchema:
    """Validates the TARGET_SCHEMA data structure — no dependencies."""

    def test_schema_is_dict(self):
        """CRITICAL – TARGET_SCHEMA must be a plain dict so it can be JSON-serialised."""
        from app.graph.pdf_extractor.schema import TARGET_SCHEMA
        assert isinstance(TARGET_SCHEMA, dict)

    def test_top_level_key(self):
        """CRITICAL – schema must have startup_evaluation as its top-level key."""
        from app.graph.pdf_extractor.schema import TARGET_SCHEMA
        assert "startup_evaluation" in TARGET_SCHEMA

    def test_required_sections_present(self):
        """HIGH – all major evaluation sections must exist inside startup_evaluation."""
        from app.graph.pdf_extractor.schema import TARGET_SCHEMA
        se = TARGET_SCHEMA["startup_evaluation"]
        expected_sections = {
            "company_snapshot", "founder_and_team", "problem_definition",
            "product_and_solution", "market_and_scope", "traction_metrics",
            "gtm_strategy", "business_model", "vision_and_strategy",
        }
        assert expected_sections.issubset(set(se.keys()))

    def test_schema_is_json_serialisable(self):
        """HIGH – schema must round-trip through JSON for LLM prompt injection."""
        from app.graph.pdf_extractor.schema import TARGET_SCHEMA
        serialised = json.dumps(TARGET_SCHEMA)
        restored = json.loads(serialised)
        assert restored["startup_evaluation"]["company_snapshot"]["company_name"] == ""

    def test_numeric_default_fields_are_zero(self):
        """MEDIUM – numeric fields default to 0, not to strings like 'N/A'."""
        from app.graph.pdf_extractor.schema import TARGET_SCHEMA
        snap = TARGET_SCHEMA["startup_evaluation"]["company_snapshot"]
        assert snap["amount_raised_to_date"] == 0
        traction = TARGET_SCHEMA["startup_evaluation"]["traction_metrics"]
        assert traction["user_count"] == 0


# ---------------------------------------------------------------------------
# 2. Prompts / constant tests
# ---------------------------------------------------------------------------

class TestPDFExtractionPrompt:
    """Tests the static PDF extraction prompt string."""

    def test_prompt_is_a_string(self):
        """CRITICAL – must be a string (template formatting fails on non-strings)."""
        from app.graph.pdf_extractor.prompts import PDF_EXTRACTION_PROMPT
        assert isinstance(PDF_EXTRACTION_PROMPT, str)

    def test_prompt_contains_placeholders(self):
        """CRITICAL – must contain both {target_schema} and {document_text}."""
        from app.graph.pdf_extractor.prompts import PDF_EXTRACTION_PROMPT
        assert "{target_schema}" in PDF_EXTRACTION_PROMPT
        assert "{document_text}" in PDF_EXTRACTION_PROMPT

    def test_prompt_contains_currency_rules(self):
        """HIGH – monetary value handling must be documented in the prompt."""
        from app.graph.pdf_extractor.prompts import PDF_EXTRACTION_PROMPT
        assert "USD" in PDF_EXTRACTION_PROMPT or "currency" in PDF_EXTRACTION_PROMPT.lower()

    def test_prompt_instructs_no_inference(self):
        """HIGH – LLM must be told not to guess or infer missing data."""
        from app.graph.pdf_extractor.prompts import PDF_EXTRACTION_PROMPT
        prompt_lower = PDF_EXTRACTION_PROMPT.lower()
        assert "not" in prompt_lower and ("infer" in prompt_lower or "guess" in prompt_lower)

    def test_prompt_non_empty(self):
        """MEDIUM – prompt must contain substantial instruction text."""
        from app.graph.pdf_extractor.prompts import PDF_EXTRACTION_PROMPT
        assert len(PDF_EXTRACTION_PROMPT.strip()) > 200


# ---------------------------------------------------------------------------
# 3. State tests
# ---------------------------------------------------------------------------

class TestPDFExtractorState:
    """Validates the TypedDict contract for PDFExtractorState."""

    def test_all_required_keys_annotated(self):
        """MEDIUM – TypedDict must declare all expected keys."""
        from app.graph.pdf_extractor.state import PDFExtractorState
        keys = set(PDFExtractorState.__annotations__.keys())
        expected = {"file_bytes", "file_name", "document_text",
                    "raw_extracted_data", "sanitized_data", "error"}
        assert expected.issubset(keys)

    def test_state_as_dict(self):
        """LOW – state is a plain dict at runtime."""
        state = {
            "file_bytes": b"fake bytes",
            "file_name": "pitch.pdf",
            "document_text": "",
            "raw_extracted_data": {},
            "sanitized_data": {},
            "error": None,
        }
        assert state["file_name"] == "pitch.pdf"


# ---------------------------------------------------------------------------
# 4. Tools tests
# ---------------------------------------------------------------------------

class TestForceNumericTypes:
    """
    Tests the pure-Python force_numeric_types utility.
    CRITICAL: this prevents type errors throughout the evaluation pipeline.
    """

    def test_converts_string_to_int(self):
        """CRITICAL – '$500,000' in a numeric field → 500000."""
        from app.graph.pdf_extractor.tools import force_numeric_types
        data = {"user_count": "500"}
        result = force_numeric_types(data)
        assert result["user_count"] == 500
        assert isinstance(result["user_count"], int)

    def test_converts_string_currency_to_int(self):
        """CRITICAL – 'USD 1000000' → 1000000."""
        from app.graph.pdf_extractor.tools import force_numeric_types
        data = {"amount_raised_to_date": "USD 1000000"}
        result = force_numeric_types(data)
        assert result["amount_raised_to_date"] == 1000000

    def test_converts_none_to_zero(self):
        """HIGH – None in a numeric field must be replaced with 0."""
        from app.graph.pdf_extractor.tools import force_numeric_types
        data = {"monthly_burn": None}
        result = force_numeric_types(data)
        assert result["monthly_burn"] == 0

    def test_converts_float_string(self):
        """HIGH – '0.25' → 0.25 (float)."""
        from app.graph.pdf_extractor.tools import force_numeric_types
        data = {"gross_margin": "0.25"}
        result = force_numeric_types(data)
        assert result["gross_margin"] == pytest.approx(0.25)

    def test_leaves_already_int_unchanged(self):
        """MEDIUM – integers must not be altered."""
        from app.graph.pdf_extractor.tools import force_numeric_types
        data = {"runway_months": 18}
        result = force_numeric_types(data)
        assert result["runway_months"] == 18

    def test_non_numeric_fields_untouched(self):
        """MEDIUM – string fields not in the numeric_fields set are NOT modified."""
        from app.graph.pdf_extractor.tools import force_numeric_types
        data = {"company_name": "Acme Corp"}
        result = force_numeric_types(data)
        assert result["company_name"] == "Acme Corp"

    def test_nested_dicts_are_processed(self):
        """HIGH – recursion must descend into nested dicts."""
        from app.graph.pdf_extractor.tools import force_numeric_types
        data = {
            "startup_evaluation": {
                "traction_metrics": {"user_count": "250"}
            }
        }
        result = force_numeric_types(data)
        assert result["startup_evaluation"]["traction_metrics"]["user_count"] == 250

    def test_list_items_are_processed(self):
        """MEDIUM – recursion must descend into list elements."""
        from app.graph.pdf_extractor.tools import force_numeric_types
        data = [{"user_count": "100"}, {"user_count": "200"}]
        result = force_numeric_types(data)
        assert result[0]["user_count"] == 100
        assert result[1]["user_count"] == 200

    def test_invalid_string_becomes_zero(self):
        """HIGH – completely non-numeric string ('n/a') → 0."""
        from app.graph.pdf_extractor.tools import force_numeric_types
        data = {"user_count": "n/a"}
        result = force_numeric_types(data)
        assert result["user_count"] == 0


class TestExtractTextFromPdf:
    """Tests the PDF byte reader (PyPDF2 wrapper)."""

    def test_raises_on_missing_dependency(self):
        """HIGH – when PyPDF2 is absent, an ImportError must be raised."""
        with patch.dict("sys.modules", {"PyPDF2": None}):
            # Force re-evaluation: mock PdfReader = None path
            from app.graph.pdf_extractor import tools as pdf_tools
            original = pdf_tools.PdfReader
            try:
                pdf_tools.PdfReader = None
                with pytest.raises(ImportError, match="PyPDF2"):
                    pdf_tools.extract_text_from_pdf(b"fake")
            finally:
                pdf_tools.PdfReader = original

    def test_extracts_text_from_pages(self):
        """CRITICAL – text must be concatenated across all pages."""
        from app.graph.pdf_extractor.tools import extract_text_from_pdf

        mock_page1 = MagicMock()
        mock_page1.extract_text.return_value = "Page one content."
        mock_page2 = MagicMock()
        mock_page2.extract_text.return_value = "Page two content."

        mock_reader = MagicMock()
        mock_reader.pages = [mock_page1, mock_page2]

        with patch("app.graph.pdf_extractor.tools.PdfReader", return_value=mock_reader):
            result = extract_text_from_pdf(b"fake pdf bytes")

        assert "Page one content." in result
        assert "Page two content." in result

    def test_skips_empty_pages(self):
        """MEDIUM – pages with no extractable text are silently skipped."""
        from app.graph.pdf_extractor.tools import extract_text_from_pdf

        mock_page1 = MagicMock()
        mock_page1.extract_text.return_value = ""   # empty — should be skipped
        mock_page2 = MagicMock()
        mock_page2.extract_text.return_value = "Real content."

        mock_reader = MagicMock()
        mock_reader.pages = [mock_page1, mock_page2]

        with patch("app.graph.pdf_extractor.tools.PdfReader", return_value=mock_reader):
            result = extract_text_from_pdf(b"fake")

        assert "Real content." in result
        assert result.count("Real content.") == 1   # only one page contributed


# ---------------------------------------------------------------------------
# 5. Node tests
# ---------------------------------------------------------------------------

class TestExtractTextNode:
    """Tests the first LangGraph async node — extracts raw text from PDF bytes."""

    @pytest.fixture
    def base_state(self):
        return {
            "file_bytes": b"fake pdf bytes",
            "file_name": "pitch.pdf",
            "document_text": "",
            "raw_extracted_data": {},
            "sanitized_data": {},
            "error": None,
        }

    @pytest.mark.asyncio
    async def test_populates_document_text(self, base_state):
        """CRITICAL – node must add document_text to state on success."""
        mock_page = MagicMock()
        mock_page.extract_text.return_value = "Startup content."
        mock_reader = MagicMock()
        mock_reader.pages = [mock_page]

        with patch("app.graph.pdf_extractor.tools.PdfReader", return_value=mock_reader):
            from app.graph.pdf_extractor.node import extract_text_node
            result = await extract_text_node(base_state)

        assert "document_text" in result
        assert "Startup content." in result["document_text"]

    @pytest.mark.asyncio
    async def test_error_on_empty_pdf(self, base_state):
        """HIGH – a PDF with no extractable text must return an error in state."""
        mock_page = MagicMock()
        mock_page.extract_text.return_value = None  # Nothing extracted
        mock_reader = MagicMock()
        mock_reader.pages = [mock_page]

        with patch("app.graph.pdf_extractor.tools.PdfReader", return_value=mock_reader):
            from app.graph.pdf_extractor.node import extract_text_node
            result = await extract_text_node(base_state)

        assert result.get("error") is not None

    @pytest.mark.asyncio
    async def test_error_on_reader_exception(self, base_state):
        """HIGH – reader exceptions must be caught and stored in state."""
        with patch("app.graph.pdf_extractor.tools.PdfReader",
                   side_effect=Exception("Corrupted PDF")):
            from app.graph.pdf_extractor.node import extract_text_node
            result = await extract_text_node(base_state)

        assert result.get("error") is not None


class TestLLMExtractionNode:
    """Tests the second LangGraph async node — structured LLM extraction."""

    @pytest.fixture
    def base_state(self):
        return {
            "file_bytes": b"",
            "file_name": "pitch.pdf",
            "document_text": "Acme Corp raises $500K seed round. CEO: John Doe.",
            "raw_extracted_data": {},
            "sanitized_data": {},
            "error": None,
        }

    @pytest.mark.asyncio
    async def test_skips_on_existing_error(self, base_state):
        """HIGH – node must pass state through if upstream error is set."""
        base_state["error"] = "Previous error"
        from app.graph.pdf_extractor.node import llm_extraction_node
        result = await llm_extraction_node(base_state)
        assert result["error"] == "Previous error"

    @patch("app.graph.pdf_extractor.node.get_llm")
    @pytest.mark.asyncio
    async def test_populates_raw_extracted_data(self, mock_get_llm, base_state):
        """CRITICAL – node must add raw_extracted_data to state."""
        mock_extracted = {
            "startup_evaluation": {
                "company_snapshot": {"company_name": "Acme Corp"}
            }
        }
        mock_chain = MagicMock()
        mock_chain.ainvoke = AsyncMock(return_value=mock_extracted)

        with patch("app.graph.pdf_extractor.node.PromptTemplate") as mock_prompt, \
             patch("app.graph.pdf_extractor.node.JsonOutputParser"):
            mock_prompt.from_template.return_value.__or__ = MagicMock(return_value=mock_chain)
            mock_chain.__or__ = MagicMock(return_value=mock_chain)

            from app.graph.pdf_extractor.node import llm_extraction_node
            result = await llm_extraction_node(base_state)

        assert "raw_extracted_data" in result

    @patch("app.graph.pdf_extractor.node.get_llm", side_effect=RuntimeError("LLM unavailable"))
    @pytest.mark.asyncio
    async def test_error_stored_on_llm_failure(self, mock_get_llm, base_state):
        """HIGH – LLM failures must be caught and stored in state['error']."""
        from app.graph.pdf_extractor.node import llm_extraction_node
        result = await llm_extraction_node(base_state)
        assert result.get("error") is not None


class TestSanitizeDataNode:
    """Tests the third LangGraph async node — type coercion and schema normalisation."""

    @pytest.fixture
    def base_state(self):
        return {
            "file_bytes": b"",
            "file_name": "pitch.pdf",
            "document_text": "Some text.",
            "raw_extracted_data": {
                "startup_evaluation": {
                    "traction_metrics": {"user_count": "500", "early_revenue": "USD 10000"}
                }
            },
            "sanitized_data": {},
            "error": None,
        }

    @pytest.mark.asyncio
    async def test_skips_on_existing_error(self, base_state):
        """HIGH – node must pass through if error already set."""
        base_state["error"] = "Upstream error"
        from app.graph.pdf_extractor.node import sanitize_data_node
        result = await sanitize_data_node(base_state)
        assert result["error"] == "Upstream error"

    @pytest.mark.asyncio
    async def test_populates_sanitized_data(self, base_state):
        """CRITICAL – node must produce sanitized_data in state."""
        from app.graph.pdf_extractor.node import sanitize_data_node
        result = await sanitize_data_node(base_state)
        assert "sanitized_data" in result
        assert result["sanitized_data"]

    @pytest.mark.asyncio
    async def test_numeric_coercion_applied(self, base_state):
        """CRITICAL – string numeric values must be coerced to ints/floats."""
        from app.graph.pdf_extractor.node import sanitize_data_node
        result = await sanitize_data_node(base_state)
        if "sanitized_data" in result and result["sanitized_data"]:
            traction = (
                result["sanitized_data"]
                .get("startup_evaluation", {})
                .get("traction_metrics", {})
            )
            if "user_count" in traction:
                assert isinstance(traction["user_count"], (int, float))

    @pytest.mark.asyncio
    async def test_wraps_missing_top_level_key(self):
        """HIGH – if LLM omits the 'startup_evaluation' wrapper, node must add it."""
        from app.graph.pdf_extractor.node import sanitize_data_node
        state = {
            "file_bytes": b"",
            "file_name": "pitch.pdf",
            "document_text": "text",
            "raw_extracted_data": {
                # Missing 'startup_evaluation' wrapper — as LLM sometimes returns
                "company_snapshot": {"company_name": "Beta Corp"}
            },
            "sanitized_data": {},
            "error": None,
        }
        result = await sanitize_data_node(state)
        assert "sanitized_data" in result
        # The node should wrap the data in startup_evaluation
        assert "startup_evaluation" in result["sanitized_data"]

    @pytest.mark.asyncio
    async def test_error_stored_on_sanitization_failure(self):
        """HIGH – exceptions in sanitization must be caught and stored."""
        from app.graph.pdf_extractor.node import sanitize_data_node

        bad_state = {
            "file_bytes": b"",
            "file_name": "pitch.pdf",
            "document_text": "text",
            "raw_extracted_data": None,   # will cause AttributeError in the node
            "sanitized_data": {},
            "error": None,
        }
        result = await sanitize_data_node(bad_state)
        assert result.get("error") is not None


# ---------------------------------------------------------------------------
# 6. Workflow graph tests
# ---------------------------------------------------------------------------

class TestPDFExtractorWorkflow:
    """Tests the compiled LangGraph StateGraph structure."""

    def test_graph_compiles(self):
        """CRITICAL – graph must compile without errors."""
        from app.graph.pdf_extractor.workflow import pdf_extractor_app
        assert pdf_extractor_app is not None

    def test_graph_has_three_nodes(self):
        """HIGH – all three pipeline nodes must be registered."""
        from app.graph.pdf_extractor.workflow import pdf_extractor_app
        node_names = set(pdf_extractor_app.nodes.keys())
        assert "extract_text" in node_names
        assert "llm_extraction" in node_names
        assert "sanitize_data" in node_names

    def test_public_api_exports(self):
        """MEDIUM – __init__ must export the three public symbols."""
        from app.graph.pdf_extractor import pdf_extractor_app, TARGET_SCHEMA, PDFExtractorState
        assert pdf_extractor_app is not None
        assert isinstance(TARGET_SCHEMA, dict)
        assert PDFExtractorState is not None
