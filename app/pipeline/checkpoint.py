"""Postgres checkpointing for the pipeline (T-034, EC-012, SP-001).

Wraps ``langgraph-checkpoint-postgres``'s ``AsyncPostgresSaver``. ``thread_id`` is
the ``document_id`` (D-SP001-1), so a crashed run resumes from its last completed
node on the next invocation. ``setup()`` (idempotent table creation) is run once
per process.

The checkpointer uses a libpq DSN (``settings.checkpoint_dsn``), not the SQLAlchemy
asyncpg URL.
"""

from __future__ import annotations

import contextlib
from collections.abc import AsyncIterator

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.graph.state import CompiledStateGraph

from app.config import get_settings
from app.pipeline.graph import compile_graph

_setup_done = False


@contextlib.asynccontextmanager
async def checkpointed_graph() -> AsyncIterator[CompiledStateGraph]:
    """Yield a compiled, Postgres-checkpointed graph for one pipeline run."""
    global _setup_done
    dsn = get_settings().checkpoint_dsn
    async with AsyncPostgresSaver.from_conn_string(dsn) as saver:
        if not _setup_done:
            await saver.setup()
            _setup_done = True
        yield compile_graph(saver)
