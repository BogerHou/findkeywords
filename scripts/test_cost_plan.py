import unittest
import json
from pathlib import Path
import tempfile

from build_cost_plan import merge_results, reasons, round_robin


CONFIG = {"broadRoots": ["online", "example", "sample", "format", "scheme", "pattern"],
          "maxPriorityNameLength": 24, "maxPriorityDigits": 2, "maxPriorityHyphens": 1}


def row(domain, root):
    name = domain.split(".")[0]
    start = name.index(root)
    return {"domain": domain, "roots": [root], "matches": [{"root": root, "start": start, "end": start + len(root)}]}


class CostPlanTests(unittest.TestCase):
    def test_new_coined_name_is_not_required_to_be_in_dictionary(self):
        self.assertEqual(reasons(row("zunavelogenerator.com", "generator"), CONFIG), [])

    def test_internal_substring_and_broad_root_are_exploration(self):
        self.assertIn("no_specific_root_at_name_edge", reasons(row("information.com", "format"), CONFIG))
        self.assertIn("broad_roots_only", reasons(row("gardeningonline.com", "online"), CONFIG))

    def test_round_robin_has_real_root_diversity_and_no_duplicate(self):
        rows = [row("agenerator.com", "generator"), row("bgenerator.com", "generator"), row("atranslator.com", "translator")]
        selected = round_robin(rows, ["generator", "translator"], 2, "test")
        self.assertEqual([r["sampling_root"] for r in selected], ["generator", "translator"])
        self.assertEqual(len({r["domain"] for r in selected}), 2)
        self.assertEqual(round_robin(rows, ["generator", "translator"], 2, "test"), selected)

    def test_multi_root_domain_does_not_consume_two_slots(self):
        mixed = {"domain": "generatortranslator.com", "roots": ["generator", "translator"]}
        selected = round_robin([mixed], ["generator", "translator"], 100, "test")
        self.assertEqual(len(selected), 1)

    def test_completed_results_can_be_reused_but_paused_batch_cannot_advance(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "results.jsonl"
            record = {"domain": "zunavelogenerator.com", "checked_at": "2026-09-28T10:00:00Z", "reason": "thin_or_empty", "stop_batch": False}
            path.write_text(json.dumps(record) + "\n")
            merged = merge_results({"records": [], "sources": []}, [path])
            self.assertEqual(merged["records"][0]["domain"], record["domain"])
            self.assertEqual(merge_results(merged, [path]), merged)
            record["stop_batch"] = True
            path.write_text(json.dumps(record) + "\n")
            with self.assertRaises(ValueError):
                merge_results(merged, [path])


if __name__ == "__main__":
    unittest.main()
