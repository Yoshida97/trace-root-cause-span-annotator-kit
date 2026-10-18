"""trace-root-cause-span-annotator-kit

Post-processes an in-memory span tree to identify the deepest error span and
annotates ancestor spans with a root-cause marker for faster incident triage.
"""

from .core import annotate_root_cause, ROOT_CAUSE_MARKER, ROOT_CAUSE_ANCESTOR_MARKER

__all__ = [
    "annotate_root_cause",
    "ROOT_CAUSE_MARKER",
    "ROOT_CAUSE_ANCESTOR_MARKER",
]
