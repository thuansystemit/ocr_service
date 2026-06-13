"""In-process cancellation registry (T-036, D-SP003-1).

A document id is added here at the start of GDPR erasure. The pipeline checks it
between nodes (and, as a cross-replica backstop, re-checks ``documents.status ==
'cancelled'`` at every persistence point) so a run that is mid-flight when erasure
begins stops writing rows that would re-create PII.
"""

from __future__ import annotations

from uuid import UUID

_cancelled: set[str] = set()


def cancel(document_id: UUID | str) -> None:
    _cancelled.add(str(document_id))


def is_cancelled(document_id: UUID | str) -> bool:
    return str(document_id) in _cancelled


def clear(document_id: UUID | str) -> None:
    _cancelled.discard(str(document_id))
