"""Prometheus metric definitions (C-20, REQ-042).

Exposed at ``/metrics`` by the API. Metric names follow the ``ocr_`` prefix
convention from the product spec.
"""

from __future__ import annotations

from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram

# A dedicated registry keeps app metrics isolated from the default global one,
# which simplifies testing and multi-process scraping.
REGISTRY = CollectorRegistry()

documents_ingested_total = Counter(
    "ocr_documents_ingested_total",
    "Documents accepted for processing.",
    labelnames=("tenant_id", "schema_name"),
    registry=REGISTRY,
)

documents_completed_total = Counter(
    "ocr_documents_completed_total",
    "Documents that finished the pipeline.",
    labelnames=("tenant_id", "routing_decision"),
    registry=REGISTRY,
)

documents_rejected_total = Counter(
    "ocr_documents_rejected_total",
    "Documents routed to the dead-letter queue.",
    labelnames=("tenant_id", "failure_reason"),
    registry=REGISTRY,
)

extraction_duration_seconds = Histogram(
    "ocr_extraction_duration_seconds",
    "End-to-end pipeline duration per document.",
    labelnames=("tenant_id", "schema_name"),
    buckets=(0.5, 1, 2, 5, 10, 15, 30, 60, 120),
    registry=REGISTRY,
)

llm_tokens_used_total = Counter(
    "ocr_llm_tokens_used_total",
    "LLM tokens consumed.",
    labelnames=("tenant_id", "model", "kind"),  # kind = input|output
    registry=REGISTRY,
)

review_queue_depth = Gauge(
    "ocr_review_queue_depth",
    "Current number of pending human-review tasks.",
    labelnames=("tenant_id",),
    registry=REGISTRY,
)
