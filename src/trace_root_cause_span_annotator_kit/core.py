"""Core algorithm for root-cause span annotation.

Given a tree of spans (parent references plus an error flag), this module
identifies the single deepest span in error and writes a marker onto it and
every ancestor up to the root, so that downstream tooling can surface the
root cause immediately without re-walking the tree.

Interpretation decisions (stated plainly, per the library's design contract):

1. Only one root cause is selected per call. When multiple spans are in error,
   we pick the one at the greatest depth (root is depth 0). Ties at the same
   depth are broken by the order of ``candidate_spans`` as supplied by the
   caller: earliest wins. This keeps the algorithm deterministic without
   inventing a ranking the caller did not ask for.

2. Cycles in parent pointers raise ``ValueError``. We do not attempt to
   "recover" from a malformed tree because doing so would silently mislabel
   the root cause, which is worse than failing loudly.

3. A span pointing to a parent id that is not in ``spans_by_id`` is treated as
   a missing reference, not a root: it raises ``ValueError``. Broken parent
   links are a data-integrity problem, not a triage problem.
"""

from __future__ import annotations

from typing import Dict, List, Mapping, MutableMapping, Tuple


ROOT_CAUSE_MARKER = "trace.root_cause.candidate"
"""Marker key written onto the span identified as the root cause."""

ROOT_CAUSE_ANCESTOR_MARKER = "trace.root_cause.ancestor"
"""Marker key written onto every ancestor of the root-cause span."""


def _compute_depths(
    spans_by_id: Mapping[str, Mapping[str, object]],
    candidate_spans: List[str],
) -> Dict[str, int]:
    """Return the depth of each candidate span, with cycle detection.

    Depth is measured in edges from the true root of the tree. We re-derive
    depth per candidate rather than computing it for every span, because the
    common case is that only a handful of spans are in error and walking the
    entire tree is wasted work.

    A defensive visited set guards against cycles: if we revisit a span id
    while climbing, the parent links are malformed and we raise rather than
    loop forever.
    """
    depths: Dict[str, int] = {}
    for span_id in candidate_spans:
        depth = 0
        current_id: str | None = span_id
        visited: set[str] = set()
        while current_id is not None:
            if current_id in visited:
                raise ValueError(
                    f"cycle detected in parent chain at span {current_id!r}"
                )
            visited.add(current_id)
            span = spans_by_id.get(current_id)
            if span is None:
                raise ValueError(
                    f"span {current_id!r} referenced but not present in spans_by_id"
                )
            parent = span.get("parent_id")
            if parent is None:
                break
            if parent not in spans_by_id:
                raise ValueError(
                    f"span {current_id!r} references missing parent {parent!r}"
                )
            depth += 1
            current_id = parent  # type: ignore[assignment]
        depths[span_id] = depth
    return depths


def _select_root_cause(
    spans_by_id: Mapping[str, Mapping[str, object]],
    error_span_ids: List[str],
) -> str | None:
    """Pick the deepest in-error span, breaking ties by input order.

    Returns ``None`` when there are no error spans.
    """
    if not error_span_ids:
        return None
    depths = _compute_depths(spans_by_id, error_span_ids)
    # max() over (depth, -index) gives the deepest span, and for ties the
    # earliest index. Using -index lets a single max() call encode both
    # rules without a separate sort.
    best_id, _ = max(
        ((span_id, (depths[span_id], -index)) for index, span_id in enumerate(error_span_ids)),
        key=lambda item: item[1],
    )
    return best_id


def _chain_to_root(
    spans_by_id: Mapping[str, Mapping[str, object]],
    leaf_id: str,
) -> List[str]:
    """Return ids from ``leaf_id`` up to the root, inclusive.

    The caller guarantees a well-formed tree, so no cycle check is repeated
    here — ``_compute_depths`` already validated every link on the path during
    selection.
    """
    chain: List[str] = []
    current_id: str | None = leaf_id
    while current_id is not None:
        chain.append(current_id)
        span = spans_by_id[current_id]
        parent = span.get("parent_id")
        current_id = parent  # type: ignore[assignment]
    return chain


def annotate_root_cause(
    spans_by_id: MutableMapping[str, MutableMapping[str, object]],
) -> Tuple[str | None, List[str]]:
    """Annotate ``spans_by_id`` in place with root-cause markers.

    Parameters
    ----------
    spans_by_id:
        A mutable mapping of span id to span dict. Each span dict must have a
        boolean ``error`` field and a ``parent_id`` field (``None`` or a key
        present in ``spans_by_id``). Spans may also carry an arbitrary
        ``attributes`` mapping, into which markers are written; if absent, an
        ``attributes`` mapping is created.

    Returns
    -------
    (root_cause_id, ancestor_ids)
        ``root_cause_id`` is ``None`` when no span is in error. ``ancestor_ids``
        lists the ids of every span strictly above the root cause (i.e. the
        root cause itself is excluded); empty when the root cause is the root
        or when there is no root cause.

    Raises
    ------
    ValueError
        On a missing parent reference or a cycle in the parent chain.
    """
    error_span_ids = [
        span_id
        for span_id, span in spans_by_id.items()
        if bool(span.get("error"))
    ]

    root_cause_id = _select_root_cause(spans_by_id, error_span_ids)
    if root_cause_id is None:
        return (None, [])

    chain = _chain_to_root(spans_by_id, root_cause_id)
    ancestor_ids = chain[1:]

    def _attrs(span: MutableMapping[str, object]) -> MutableMapping[str, object]:
        attrs = span.get("attributes")
        if attrs is None:
            attrs = {}
            span["attributes"] = attrs
        if not isinstance(attrs, dict):
            raise TypeError(
                f"span attributes must be a dict or absent, got {type(attrs).__name__}"
            )
        return attrs  # type: ignore[return-value]

    root_cause_span = spans_by_id[root_cause_id]
    _attrs(root_cause_span)[ROOT_CAUSE_MARKER] = True

    for ancestor_id in ancestor_ids:
        ancestor_span = spans_by_id[ancestor_id]
        _attrs(ancestor_span)[ROOT_CAUSE_ANCESTOR_MARKER] = True

    return (root_cause_id, ancestor_ids)
