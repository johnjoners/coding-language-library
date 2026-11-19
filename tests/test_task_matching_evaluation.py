"""Evaluation set for task matching: jobs, acceptable choices, and expected explanations."""

import json
import unittest
from pathlib import Path

from mcp.task_matching import compare_candidates, get_suitability_evidence, recommend_stack

ROOT = Path(__file__).resolve().parents[1]
PROFILES = json.loads((ROOT / "data/suitability_profiles.json").read_text(encoding="utf-8"))

WEBHOOK_SERVICE = {
    "task": "Build a webhook-processing service",
    "existing_project": {"languages": [], "frameworks": []},
    "target": {"platform": "linux", "deployment": "container"},
    "requirements": {"required_integrations": ["HTTP", "PostgreSQL"]},
    "priorities": ["delivery_speed"],
    "team_experience": [],
    "unknowns": ["expected_request_volume"],
}

INCUMBENT_JAVA = {
    **WEBHOOK_SERVICE,
    "task": "Extend a Java order service with a webhook endpoint",
    "existing_project": {"languages": ["Java"], "frameworks": ["Spring Boot"]},
}

INCUMBENT_GO = {
    **WEBHOOK_SERVICE,
    "task": "Extend a Go order service with a webhook endpoint",
    "existing_project": {"languages": ["Go"], "frameworks": ["net/http"]},
}

DISQUALIFIED_MEMORY = {
    **WEBHOOK_SERVICE,
    "requirements": {"required_integrations": ["HTTP"], "memory_limit_mb": 64},
}


class TaskMatchingEvaluationTests(unittest.TestCase):
    def test_webhook_service_keeps_all_stacks_and_exposes_unmeasured_constraints(self):
        """All curated stacks stay eligible; nothing is guessed as passed."""
        result = recommend_stack(WEBHOOK_SERVICE, PROFILES, limit=20)
        self.assertEqual(len(result), 5)
        for row in result:
            self.assertEqual(row["hard_constraints"]["failed"], [])
            self.assertNotIn("integration.http", row["hard_constraints"]["failed"])
            self.assertIn("integration.postgresql", row["hard_constraints"]["unknown"],
                          "conditional PostgreSQL support must stay unknown until its conditions are checked")
            self.assertIn("target.platform=linux", row["hard_constraints"]["unknown"])
            self.assertIn("target.deployment=container", row["hard_constraints"]["unknown"])
            self.assertEqual(row["verification_status"], "source_documented")
            self.assertEqual(row["open_questions"], ["expected_request_volume"])
            self.assertTrue(row["tradeoffs"], "each stack must state a tradeoff")
            self.assertTrue(row["next_validation"], "each stack must state a validation step")

    def test_memory_limit_stays_unknown_when_no_profile_measures_it(self):
        result = recommend_stack(DISQUALIFIED_MEMORY, PROFILES, limit=20)
        self.assertEqual(len(result), 5)
        for row in result:
            self.assertTrue(any(value.startswith("requirements.memory_limit_mb")
                                for value in row["hard_constraints"]["unknown"]))

    def test_incumbent_java_project_ranks_the_java_stack_first(self):
        result = recommend_stack(INCUMBENT_JAVA, PROFILES, limit=5)
        self.assertEqual(result[0]["candidate"]["stack_id"], "java-spring-boot-pgjdbc")
        self.assertTrue(any("existing project language" in reason for reason in result[0]["reasons"]))
        self.assertTrue(any("framework already used" in reason for reason in result[0]["reasons"]))
        self.assertGreater(result[0]["rank_score"], result[1]["rank_score"])

    def test_incumbent_go_project_ranks_the_go_stack_first(self):
        result = recommend_stack(INCUMBENT_GO, PROFILES, limit=5)
        self.assertEqual(result[0]["candidate"]["stack_id"], "go-net-http-pgx")
        self.assertGreater(result[0]["rank_score"], result[1]["rank_score"])

    def test_unevidenced_priority_is_reported_not_scored(self):
        result = recommend_stack(WEBHOOK_SERVICE, PROFILES, limit=5)
        for row in result:
            self.assertEqual(row["rank_score"], 0)
            self.assertTrue(any("No profile evidence ranks these priorities" in reason
                                for reason in row["reasons"]))

    def test_duplicated_or_missing_candidates_fail_closed(self):
        with self.assertRaises(ValueError):
            compare_candidates(["go-net-http-pgx", "go-net-http-pgx"], WEBHOOK_SERVICE, PROFILES)
        with self.assertRaises(ValueError):
            compare_candidates(["no-such-stack"], WEBHOOK_SERVICE, PROFILES)

    def test_evidence_lookup_returns_https_sources_for_every_claim_with_evidence(self):
        for stack in PROFILES["stacks"]:
            result = get_suitability_evidence(stack["language_id"], None, PROFILES)
            self.assertTrue(result["claims"])
            for claim in result["claims"]:
                for source in claim.get("evidence", []):
                    self.assertTrue(source["source_url"].startswith("https://"))
                    self.assertTrue(source["checked_at"])
                    self.assertTrue(source["applies_to"])


if __name__ == "__main__":
    unittest.main()