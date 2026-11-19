import unittest

from mcp.task_matching import compare_candidates, get_suitability_evidence, recommend_stack


SOURCE = {
    "source_url": "https://example.invalid/docs",
    "checked_at": "2026-11-19",
    "applies_to": "test fixture",
}


def claim(status, capability):
    return {
        "status": status,
        "conditions": [],
        "evidence": [{**SOURCE, "capability": capability}],
    }


PROFILES = {
    "schema_version": 1,
    "stacks": [
        {
            "id": "go-pgx",
            "language_id": "go",
            "language_name": "Go",
            "framework": "net/http",
            "runtime": "Go toolchain",
            "verification_status": "source_documented",
            "capabilities": {
                "platform.linux": claim("supported", "platform.linux"),
                "integration.http": claim("supported", "integration.http"),
                "integration.postgresql": claim("supported", "integration.postgresql"),
                "deployment.container": claim("supported", "deployment.container"),
                "resources.memory_peak_mb": {"status": "unknown", "evidence": []},
                "dependencies.native": {"status": "unknown", "evidence": []},
            },
            "preference_signals": {},
        },
        {
            "id": "java-spring",
            "language_id": "java",
            "language_name": "Java",
            "framework": "Spring Boot",
            "runtime": "JVM",
            "capabilities": {
                "platform.linux": claim("supported", "platform.linux"),
                "integration.http": claim("supported", "integration.http"),
                "integration.postgresql": claim("unsupported", "integration.postgresql"),
                "deployment.container": claim("supported", "deployment.container"),
            },
            "preference_signals": {},
        },
    ],
}


TASK = {
    "task": "Build a webhook service",
    "existing_project": {"languages": [], "frameworks": []},
    "target": {"platform": "linux", "deployment": "container"},
    "requirements": {
        "required_integrations": ["HTTP", "PostgreSQL"],
        "memory_limit_mb": 256,
        "native_dependencies_allowed": False,
    },
    "priorities": ["delivery_speed", "maintainability"],
    "team_experience": [],
    "unknowns": [],
}


class TaskMatchingTests(unittest.TestCase):
    def test_recommendation_rejects_evidenced_hard_constraint_failure(self):
        result = recommend_stack(TASK, PROFILES)
        self.assertEqual([row["candidate"]["stack_id"] for row in result], ["go-pgx"])
        self.assertEqual(result[0]["hard_constraints"]["failed"], [])
        self.assertIn("integration.postgresql", result[0]["hard_constraints"]["passed"])

    def test_unknown_constraints_are_reported_not_guessed_or_rejected(self):
        result = recommend_stack(TASK, PROFILES)[0]
        unknown = result["hard_constraints"]["unknown"]
        self.assertTrue(any(value.startswith("requirements.memory_limit_mb") for value in unknown))
        self.assertTrue(any(value.startswith("requirements.native_dependencies_allowed") for value in unknown))
        self.assertEqual(result["verification_status"], "source_documented")

    def test_existing_project_and_team_experience_affect_explainable_order(self):
        task = {**TASK, "existing_project": {"languages": ["java"], "frameworks": []}}
        result = recommend_stack(task, PROFILES)
        # The incumbent is still shown, but an evidenced hard failure remains disqualifying.
        self.assertEqual([row["candidate"]["stack_id"] for row in result], ["go-pgx"])
        task = {**TASK, "requirements": {"required_integrations": ["HTTP"]}}
        task["existing_project"] = {"languages": ["java"], "frameworks": []}
        result = recommend_stack(task, PROFILES)
        self.assertEqual([row["candidate"]["stack_id"] for row in result][0], "java-spring")
        self.assertTrue(any(reason.startswith("Matches an existing project language") for reason in result[0]["reasons"]))

    def test_compare_uses_same_checks_and_ranking_as_recommendation(self):
        compared = compare_candidates(["go-pgx", "java-spring"], TASK, PROFILES)
        recommended = recommend_stack(TASK, PROFILES)
        self.assertEqual([row["candidate"]["stack_id"] for row in compared], ["go-pgx", "java-spring"])
        self.assertEqual([row["candidate"]["stack_id"] for row in recommended], ["go-pgx"])
        self.assertIn("integration.postgresql", compared[1]["hard_constraints"]["failed"])

    def test_evidence_lookup_returns_exact_claims(self):
        evidence = get_suitability_evidence("go", "integration.postgresql", PROFILES)
        self.assertEqual(evidence["language_id"], "go")
        self.assertEqual(evidence["capability"], "integration.postgresql")
        self.assertEqual(evidence["claims"][0]["status"], "supported")

    def test_priority_order_sets_descending_weight_only_when_signal_has_evidence(self):
        profiles = {"schema_version": 1, "stacks": [
            {**PROFILES["stacks"][0], "preference_signals": {"delivery_speed": {"status": "supported", "evidence": [SOURCE]}}},
            {**PROFILES["stacks"][1], "preference_signals": {"maintainability": {"status": "supported", "evidence": [SOURCE]}}},
        ]}
        task = {**TASK, "requirements": {}}
        ranked = recommend_stack(task, profiles)
        self.assertEqual(ranked[0]["candidate"]["stack_id"], "go-pgx")
        self.assertEqual(ranked[0]["rank_score"], 20)
        self.assertEqual(ranked[1]["rank_score"], 10)

    def test_conditional_support_is_unknown_until_conditions_are_checked(self):
        profiles = {**PROFILES, "stacks": [
            {**PROFILES["stacks"][0], "capabilities": {
                **PROFILES["stacks"][0]["capabilities"],
                "integration.postgresql": {
                    **claim("supported_with_conditions", "integration.postgresql"),
                    "conditions": ["Driver must be configured."],
                },
            }}
        ]}
        task = {**TASK, "requirements": {"required_integrations": ["PostgreSQL"]}}
        result = recommend_stack(task, profiles)[0]
        self.assertIn("integration.postgresql", result["hard_constraints"]["unknown"])
        self.assertNotIn("integration.postgresql", result["hard_constraints"]["passed"])

    def test_recommendation_preserves_task_unknowns(self):
        task = {**TASK, "unknowns": ["expected_request_volume"], "requirements": {}}
        result = recommend_stack(task, PROFILES)[0]
        self.assertEqual(result["open_questions"], ["expected_request_volume"])

    def test_real_profiles_link_to_inventory_and_carry_evidence_metadata(self):
        import json
        from pathlib import Path

        root = Path(__file__).resolve().parents[1]
        inventory = json.loads((root / "data/inventory.json").read_text())
        profiles = json.loads((root / "data/suitability_profiles.json").read_text())
        language_ids = {row["id"] for row in inventory["languages"]}
        self.assertTrue(profiles["stacks"])
        for stack in profiles["stacks"]:
            self.assertIn(stack["language_id"], language_ids)
            self.assertEqual(stack["verification_status"], "source_documented")
            for claim_data in stack["capabilities"].values():
                for source in claim_data.get("evidence", []):
                    self.assertTrue(source["source_url"].startswith("https://"))
                    self.assertTrue(source["checked_at"])
                    self.assertTrue(source["applies_to"])

    def test_mcp_registers_recommendation_and_evidence_tools(self):
        from mcp.server import TOOLS

        self.assertTrue({"recommend_stack", "compare_candidates", "get_suitability_evidence"} <= set(TOOLS))

    def test_constraint_terms_left_in_prose_are_flagged_not_parsed(self):
        task = {"task": "Build a webhook service that stays under 256 MB with no native dependencies"}
        result = recommend_stack(task, PROFILES)
        self.assertIn("requirements.memory_limit_mb", result[0]["unstructured_terms"])
        self.assertIn("requirements.native_dependencies_allowed", result[0]["unstructured_terms"])
        compared = compare_candidates(["go-pgx", "java-spring"], task, PROFILES)
        self.assertEqual(compared[0]["unstructured_terms"], result[0]["unstructured_terms"])
        structured = {**task, "requirements": {"memory_limit_mb": 256, "native_dependencies_allowed": False}}
        self.assertEqual(recommend_stack(structured, PROFILES)[0]["unstructured_terms"], [])

    def test_prose_lint_uses_word_boundaries_not_substrings(self):
        from mcp.task_matching import _unstructured_terms
        self.assertEqual(_unstructured_terms({"task": "Rewrite the climbing log in a frameworked style"}), [])
        self.assertEqual(_unstructured_terms({"task": "Serve 3 GB of media files"}),
                         ["requirements.memory_limit_mb"])
        self.assertEqual(_unstructured_terms({"task": "Sync calendar events", "requirements": {"required_integrations": ["Calendar"]}}), [])

    def test_invalid_or_ambiguous_candidate_identifiers_fail_closed(self):
        with self.assertRaises(ValueError):
            compare_candidates(["missing"], TASK, PROFILES)
        duplicated = {**PROFILES, "stacks": PROFILES["stacks"] + [PROFILES["stacks"][0]]}
        with self.assertRaises(ValueError):
            recommend_stack(TASK, duplicated)


if __name__ == "__main__":
    unittest.main()
