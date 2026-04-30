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
    "pptx",
    "fitz",                     # PyMuPDF
    "neo4j",
    "neo4j.time",
]
for _mod in _OPTIONAL_STUBS:
    if _mod not in sys.modules:
        sys.modules[_mod] = MagicMock()

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
    """
    noop = _make_noop_ctx()

    modules_to_patch = [
        "app.core.limiter.concurrency_limiter",
        "app.graph.evaluation_agent.tools.vision_tools.concurrency_limiter",
        "app.graph.evaluation_agent.tools.business_tools.concurrency_limiter",
        "app.graph.evaluation_agent.tools.gtm_tools.concurrency_limiter",
        "app.graph.evaluation_agent.tools.operations_tools.concurrency_limiter",
        "app.graph.evaluation_agent.tools.problem_tools.concurrency_limiter",
        "app.graph.evaluation_agent.tools.product_tools.concurrency_limiter",
        "app.graph.evaluation_agent.tools.team_tools.concurrency_limiter",
        "app.graph.evaluation_agent.tools.traction_tools.concurrency_limiter",
        "app.graph.evaluation_agent.tools.general_tools.concurrency_limiter",
        "app.graph.evaluation_agent.tools.market_tools.concurrency_limiter",
    ]

    patchers = [patch(target, noop) for target in modules_to_patch]
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
