# trace-root-cause-span-annotator-kit

Post-processes an in-memory span tree to identify the deepest error span and annotates ancestor spans with a root-cause marker for faster incident triage.

## Usage

```python
from trace_root_cause_span_annotator_kit import (
    annotate_root_cause,
    ROOT_CAUSE_MARKER,
    ROOT_CAUSE_ANCESTOR_MARKER,
)

spans = {
    "root": {"id": "root", "parent_id": None, "error": False, "attributes": {}},
    "auth": {"id": "auth", "parent_id": "root", "error": False, "attributes": {}},
    "db":   {"id": "db",   "parent_id": "auth", "error": True,  "attributes": {}},
}

root_cause_id, ancestor_ids = annotate_root_cause(spans)
# root_cause_id == "db"
# ancestor_ids  == ["auth", "root"]

# spans["db"]["attributes"][ROOT_CAUSE_MARKER] is True
# spans["auth"]["attributes"][ROOT_CAUSE_ANCESTOR_MARKER] is True
# spans["root"]["attributes"][ROOT_CAUSE_ANCESTOR_MARKER] is True
```

## Why this exists

When a distributed trace fails, the error usually surfaces on several spans at once — the failing call and every parent that propagated or observed the failure. Triage tooling that walks the tree at query time to find the origin is doing redundant work on every page. This library does that walk once, up front, and writes markers into `span.attributes` so downstream readers can short-circuit straight to the root cause.

The trade-off: we pick exactly one root cause per call. When multiple sibling spans are in error at the same depth, the earliest in iteration order wins. A "rank all candidates" policy would require ranking data this library deliberately does not ask for, so we keep the contract narrow and deterministic.

## Edge you will hit

`error` is treated as truthy Python, not strictly boolean. A span with `"error": "false"` (a non-empty string) will be treated as an error. Normalise your spans upstream if that matters to you.

Parent links must resolve. A span whose `parent_id` refers to an id not present in the mapping, or whose parent chain forms a cycle, raises `ValueError` — we fail loudly rather than silently mislabelling the root cause.

If a span has no `attributes` mapping, one is created. If it has `attributes` set to a non-dict (e.g. a list), `TypeError` is raised.

## Running the tests

```
PYTHONPATH=src python -m unittest discover -s tests
```
