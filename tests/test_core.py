import unittest

from trace_root_cause_span_annotator_kit import (
    annotate_root_cause,
    ROOT_CAUSE_MARKER,
    ROOT_CAUSE_ANCESTOR_MARKER,
)


class AnnotateRootCauseTests(unittest.TestCase):
    def _span(self, span_id, parent_id=None, error=False, attributes=None):
        return {
            "id": span_id,
            "parent_id": parent_id,
            "error": error,
            "attributes": dict(attributes) if attributes else {},
        }

    def test_no_errors_returns_none_and_empty_ancestors(self):
        spans = {
            "a": self._span("a"),
            "b": self._span("b", "a"),
        }
        root_cause, ancestors = annotate_root_cause(spans)
        self.assertIsNone(root_cause)
        self.assertEqual(ancestors, [])
        # No markers written.
        self.assertEqual(spans["a"]["attributes"], {})
        self.assertEqual(spans["b"]["attributes"], {})

    def test_single_error_is_root_cause(self):
        spans = {
            "a": self._span("a"),
            "b": self._span("b", "a", error=True),
        }
        root_cause, ancestors = annotate_root_cause(spans)
        self.assertEqual(root_cause, "b")
        self.assertEqual(ancestors, ["a"])
        self.assertTrue(spans["b"]["attributes"].get(ROOT_CAUSE_MARKER))
        self.assertTrue(spans["a"]["attributes"].get(ROOT_CAUSE_ANCESTOR_MARKER))

    def test_deepest_error_wins(self):
        spans = {
            "a": self._span("a", error=True),
            "b": self._span("b", "a", error=True),
            "c": self._span("c", "b", error=True),
        }
        root_cause, ancestors = annotate_root_cause(spans)
        self.assertEqual(root_cause, "c")
        self.assertEqual(ancestors, ["b", "a"])
        self.assertTrue(spans["c"]["attributes"].get(ROOT_CAUSE_MARKER))
        self.assertTrue(spans["b"]["attributes"].get(ROOT_CAUSE_ANCESTOR_MARKER))
        self.assertTrue(spans["a"]["attributes"].get(ROOT_CAUSE_ANCESTOR_MARKER))

    def test_shallower_error_is_marked_as_ancestor_only(self):
        spans = {
            "root": self._span("root", error=True),
            "child": self._span("child", "root", error=True),
        }
        root_cause, ancestors = annotate_root_cause(spans)
        self.assertEqual(root_cause, "child")
        self.assertEqual(ancestors, ["root"])
        # Root is an ancestor, NOT the root cause.
        self.assertNotIn(ROOT_CAUSE_MARKER, spans["root"]["attributes"])
        self.assertTrue(spans["root"]["attributes"].get(ROOT_CAUSE_ANCESTOR_MARKER))

    def test_tie_breaked_by_input_order(self):
        # Two sibling error spans at the same depth; 'a' is inserted first.
        spans = {}
        spans["a"] = self._span("a", "root", error=True)
        spans["root"] = self._span("root")
        spans["b"] = self._span("b", "root", error=True)
        root_cause, ancestors = annotate_root_cause(spans)
        self.assertEqual(root_cause, "a")
        self.assertEqual(ancestors, ["root"])
        self.assertNotIn(ROOT_CAUSE_MARKER, spans["b"]["attributes"])

    def test_creates_attributes_when_absent(self):
        spans = {
            "a": {"id": "a", "parent_id": None, "error": False},
            "b": {"id": "b", "parent_id": "a", "error": True},
        }
        root_cause, ancestors = annotate_root_cause(spans)
        self.assertEqual(root_cause, "b")
        self.assertEqual(ancestors, ["a"])
        self.assertIn("attributes", spans["b"])
        self.assertTrue(spans["b"]["attributes"].get(ROOT_CAUSE_MARKER))
        self.assertTrue(spans["a"]["attributes"].get(ROOT_CAUSE_ANCESTOR_MARKER))

    def test_preserves_existing_attributes(self):
        spans = {
            "a": self._span("a", attributes={"http.status": 500}),
            "b": self._span("b", "a", error=True, attributes={"db.system": "postgres"}),
        }
        annotate_root_cause(spans)
        self.assertEqual(spans["a"]["attributes"]["http.status"], 500)
        self.assertEqual(spans["b"]["attributes"]["db.system"], "postgres")
        self.assertTrue(spans["b"]["attributes"].get(ROOT_CAUSE_MARKER))

    def test_missing_parent_raises_value_error(self):
        spans = {
            "a": self._span("a", "nonexistent", error=True),
        }
        with self.assertRaises(ValueError):
            annotate_root_cause(spans)

    def test_cycle_raises_value_error(self):
        spans = {
            "a": self._span("a", "b"),
            "b": self._span("b", "a", error=True),
        }
        with self.assertRaises(ValueError):
            annotate_root_cause(spans)

    def test_error_must_be_truthy_not_just_truthy_string(self):
        # "false" is truthy in Python; we only honour actual booleans per the
        # contract. This documents that choice.
        spans = {
            "a": {"id": "a", "parent_id": None, "error": "false"},
        }
        root_cause, ancestors = annotate_root_cause(spans)
        self.assertEqual(root_cause, "a")
        self.assertEqual(ancestors, [])

    def test_single_root_span_in_error(self):
        spans = {
            "only": self._span("only", error=True),
        }
        root_cause, ancestors = annotate_root_cause(spans)
        self.assertEqual(root_cause, "only")
        self.assertEqual(ancestors, [])
        self.assertTrue(spans["only"]["attributes"].get(ROOT_CAUSE_MARKER))

    def test_attributes_not_a_dict_raises_type_error(self):
        spans = {
            "a": {"id": "a", "parent_id": None, "error": False, "attributes": []},
            "b": {"id": "b", "parent_id": "a", "error": True, "attributes": []},
        }
        with self.assertRaises(TypeError):
            annotate_root_cause(spans)


if __name__ == "__main__":
    unittest.main()
