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

import pytest
from unittest.mock import patch, AsyncMock, MagicMock


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
    for p in patchers:
        p.start()

    yield

    for p in patchers:
        p.stop()
