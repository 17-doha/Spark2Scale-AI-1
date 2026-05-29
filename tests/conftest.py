"""
tests/conftest.py
=================
Test-level fixtures shared across all evaluation tests.

KEY FIX: The `concurrency_limiter` in `app.core.limiter` is an
`asyncio.Semaphore(2)` created at module import time.  In Python 3.10+ /
pytest-asyncio >=0.21, each async test runs in its own event loop, so the
pre-created Semaphore is bound to a DIFFERENT loop → `async with
concurrency_limiter` hangs forever.

The `patch_concurrency_limiter` autouse fixture patches every module-level
reference to `concurrency_limiter` with a plain `MagicMock` whose
`__aenter__` / `__aexit__` are no-ops so the `async with` block passes
through without ever touching a real Semaphore.
"""

import sys
from unittest.mock import MagicMock

# ---------------------------------------------------------------------------
# Stub optional heavy dependencies that may not be installed in the test venv.
# This must happen BEFORE any app module is imported so module-level imports
# like `from langchain_groq import ChatGroq` don't raise ModuleNotFoundError.
# ---------------------------------------------------------------------------
_OPTIONAL_STUBS = [
    "langchain_groq",
    "langchain_community",
    "langchain_community.chat_models",
    "langchain_community.chat_models.ChatOllama",
    # pptx — stub the top-level package and every submodule the ppt_generation_agent
    # imports, so `from pptx.enum.text import PP_ALIGN` etc. resolve to MagicMocks
    # instead of raising ModuleNotFoundError during test collection.
    "pptx",
    "pptx.enum",
    "pptx.enum.text",
    "pptx.enum.shapes",
    "pptx.util",
    "pptx.dml",
    "pptx.dml.color",
    "pptx.opc",
    "pptx.opc.constants",
    "pptx.oxml",
    "pptx.oxml.xmlchemy",
    "pptx.shapes",
    "pptx.shapes.autoshape",
    "pptx.slide",
    "pptx.text",
    "pptx.text.text",
    "fitz",                     # PyMuPDF
    "neo4j",
    "neo4j.time",
    # Additional optional heavy dependencies not installed in the unit-test env
    "yfinance",                 # used by competitor_analysis_agent
    "builtwith",                # used by product_tools / tech_stack_detective
    "arabic_reshaper",          # used by market_research PDF rendering
    "bidi",                     # arabic_reshaper companion (BiDi algorithm)
    "bidi.algorithm",
    "langchain_openai",         # used by pitch_analyzer agent
    "pytrends",                 # used by market_research & competitor_analysis agents
    "pytrends.request",
]
for _mod in _OPTIONAL_STUBS:
    if _mod not in sys.modules:
        sys.modules[_mod] = MagicMock()

# ---------------------------------------------------------------------------
# json_repair MUST be a real passthrough, NOT a MagicMock.
#
# helpers.py does: from json_repair import repair_json
#                  parsed = json.loads(repair_json(cleaned_text))
#
# If repair_json is a MagicMock, repair_json(string) returns a MagicMock and
# json.loads(MagicMock()) raises TypeError → every test falls back to "0/5".
#
# The real json_repair library may or may not be installed.  Either way, we
# ensure the module exposes a real callable passthrough so unit tests work.
# ---------------------------------------------------------------------------
import types as _types
import importlib as _importlib

import ast as _ast
import json as _json

def _passthrough_repair_json(s, *args, **kwargs):  # noqa: ANN001
    """
    Repair-JSON passthrough for unit tests.

    The real json_repair library handles single-quoted dicts, trailing commas,
    etc.  When it's not installed we approximate that with ast.literal_eval,
    which handles Python dict literals (single quotes, trailing commas).

    Always returns a *string* (because callers do json.loads(repair_json(s))).
    """
    if not isinstance(s, str):
        return str(s)
    # Fast path: already valid JSON — return as-is
    try:
        _json.loads(s)
        return s
    except (_json.JSONDecodeError, ValueError):
        pass
    # Fallback: Python literal eval (handles single quotes + trailing commas)
    try:
        obj = _ast.literal_eval(s)
        return _json.dumps(obj)
    except Exception:
        # Give up — return original string and let the caller handle the error
        return s

try:
    # Try to use the real library if installed
    _real_json_repair = _importlib.import_module("json_repair")
    if not callable(getattr(_real_json_repair, "repair_json", None)):
        _real_json_repair.repair_json = _passthrough_repair_json
    sys.modules["json_repair"] = _real_json_repair
except (ImportError, ModuleNotFoundError):
    # Library not installed — build a minimal stub module
    _json_repair_stub = _types.ModuleType("json_repair")
    _json_repair_stub.repair_json = _passthrough_repair_json
    sys.modules["json_repair"] = _json_repair_stub

import pytest
from unittest.mock import patch, AsyncMock


def _make_noop_ctx():
    """Return an async context manager that does nothing."""
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=None)
    ctx.__aexit__ = AsyncMock(return_value=False)
    return ctx


@pytest.fixture(autouse=True)
def patch_concurrency_limiter():
    """
    Replace every imported reference to `concurrency_limiter` with a
    no-op async context manager so tests never block on the Semaphore.

    Also patches `repair_json` in helpers.py with a real passthrough so that
    parse_and_repair_json works correctly when json_repair was stubbed as a
    MagicMock during collection-time import.
    """
    noop = _make_noop_ctx()

    _limiter_names = ["groq_limiter", "modal_limiter", "concurrency_limiter"]
    _tool_modules = [
        "vision_tools", "business_tools", "gtm_tools", "operations_tools",
        "problem_tools", "product_tools", "team_tools", "traction_tools",
        "general_tools", "market_tools",
    ]
    modules_to_patch = [
        f"app.core.limiter.{lim}" for lim in _limiter_names
    ] + [
        f"app.graph.evaluation_agent.tools.{mod}.{lim}"
        for mod in _tool_modules
        for lim in _limiter_names
    ]

    patchers = [patch(target, noop) for target in modules_to_patch]

    # Patch the bound repair_json name in all modules that do
    # `from json_repair import repair_json` so that even if those modules were
    # imported before conftest ran (binding MagicMock), tests see the real
    # passthrough callable.
    for _repair_target in [
        "app.graph.evaluation_agent.helpers.repair_json",
        "app.graph.BMC.node.repair_json",
    ]:
        patchers.append(
            patch(_repair_target, side_effect=_passthrough_repair_json)
        )

    started = []
    for p in patchers:
        try:
            p.start()
            started.append(p)
        except AttributeError:
            # Module not imported in this test session — safe to skip
            pass

    yield

    for p in started:
        p.stop()
