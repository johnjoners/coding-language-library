"""Evidence-backed, deterministic task-to-stack matching."""

from __future__ import annotations

import math
from typing import Any


MAX_RESULTS = 20
CAPABILITY_STATUSES = {"supported", "supported_with_conditions", "unsupported", "unknown"}
VERIFICATION_STATUSES = {"catalogue_only", "source_documented", "environment_checked", "project_tested"}
RANK_WEIGHTS = {
    "existing_language": 100,
    "existing_framework": 60,
    "team_experience": 20,
    "priority_step": 10,
    "priority_cap": 60,
}


def _norm(value: str) -> str:
    return "".join(char for char in value.casefold() if char.isalnum() or char in "+#")


def _validate_evidence(evidence: Any, context: str) -> None:
    if not isinstance(evidence, list):
        raise ValueError(f"{context}.evidence must be a list")
    for index, item in enumerate(evidence):
        if not isinstance(item, dict):
            raise ValueError(f"{context}.evidence[{index}] must be an object")
        for field in ("source_url", "checked_at", "applies_to"):
            value = item.get(field)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{context}.evidence[{index}].{field} is required")
        if not item["source_url"].startswith("https://"):
            raise ValueError(f"{context}.evidence[{index}].source_url must use HTTPS")


def _profiles(profiles: dict[str, Any]) -> list[dict[str, Any]]:
    if not isinstance(profiles, dict) or profiles.get("schema_version") != 1:
        raise ValueError("unsupported suitability profile schema")
    stacks = profiles.get("stacks")
    if not isinstance(stacks, list):
        raise ValueError("suitability profiles must contain a stacks list")
    ids: list[str] = []
    for index, stack in enumerate(stacks):
        context = f"stacks[{index}]"
        if not isinstance(stack, dict):
            raise ValueError(f"{context} must be an object")
        for field in ("id", "language_id", "language_name"):
            value = stack.get(field)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{context}.{field} must be a non-empty string")
        ids.append(stack["id"])
        for field in ("framework", "runtime"):
            value = stack.get(field)
            if value is not None and not isinstance(value, str):
                raise ValueError(f"{context}.{field} must be a string")
        frameworks = stack.get("frameworks", [])
        if not isinstance(frameworks, list) or any(not isinstance(value, str) or not value.strip() for value in frameworks):
            raise ValueError(f"{context}.frameworks must be a list of non-empty strings")
        verification = stack.get("verification_status", "catalogue_only")
        if not isinstance(verification, str) or verification not in VERIFICATION_STATUSES:
            raise ValueError(f"{context}.verification_status is invalid")
        capabilities = stack.get("capabilities", {})
        if not isinstance(capabilities, dict):
            raise ValueError(f"{context}.capabilities must be an object")
        for key, claim in capabilities.items():
            claim_context = f"{context}.capabilities.{key}"
            if not isinstance(key, str) or not key or not isinstance(claim, dict):
                raise ValueError(f"{claim_context} must be a named object")
            status = claim.get("status", "unknown")
            if not isinstance(status, str) or status not in CAPABILITY_STATUSES:
                raise ValueError(f"{claim_context}.status is invalid")
            conditions = claim.get("conditions", [])
            if not isinstance(conditions, list) or any(not isinstance(value, str) for value in conditions):
                raise ValueError(f"{claim_context}.conditions must be a list of strings")
            _validate_evidence(claim.get("evidence", []), claim_context)
        signals = stack.get("preference_signals", {})
        if not isinstance(signals, dict):
            raise ValueError(f"{context}.preference_signals must be an object")
        for name, signal in signals.items():
            signal_context = f"{context}.preference_signals.{name}"
            if not isinstance(name, str) or not name or not isinstance(signal, dict):
                raise ValueError(f"{signal_context} must be a named object")
            status = signal.get("status", "unknown")
            if not isinstance(status, str) or status not in CAPABILITY_STATUSES:
                raise ValueError(f"{signal_context}.status is invalid")
            _validate_evidence(signal.get("evidence", []), signal_context)
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate stack identifiers")
    return stacks


def _validate_task(task: dict[str, Any]) -> None:
    if not isinstance(task, dict) or not isinstance(task.get("task"), str) or not task["task"].strip():
        raise ValueError("task_profile.task must be a non-empty string")
    allowed = {"task", "existing_project", "target", "requirements", "priorities", "team_experience", "unknowns"}
    extra = set(task) - allowed
    if extra:
        raise ValueError("unsupported task_profile fields: " + ", ".join(sorted(extra)))
    section_fields = {
        "existing_project": {"languages", "frameworks"},
        "target": {"platform", "deployment"},
        "requirements": {"required_integrations", "memory_limit_mb", "native_dependencies_allowed"},
    }
    for section, allowed_fields in section_fields.items():
        value = task.get(section, {})
        if not isinstance(value, dict):
            raise ValueError(f"task_profile.{section} must be an object")
        extra = set(value) - allowed_fields
        if extra:
            raise ValueError(f"unsupported task_profile.{section} fields: " + ", ".join(sorted(extra)))
    existing = task.get("existing_project", {})
    for field in ("languages", "frameworks"):
        values = existing.get(field, [])
        if not isinstance(values, list) or any(not isinstance(value, str) or not value.strip() for value in values):
            raise ValueError(f"task_profile.existing_project.{field} must be a list of non-empty strings")
    target = task.get("target", {})
    for field in ("platform", "deployment"):
        if field in target and (not isinstance(target[field], str) or not target[field].strip()):
            raise ValueError(f"task_profile.target.{field} must be a non-empty string")
    requirements = task.get("requirements", {})
    integrations = requirements.get("required_integrations", [])
    if not isinstance(integrations, list) or any(not isinstance(value, str) or not value.strip() for value in integrations):
        raise ValueError("task_profile.requirements.required_integrations must be a list of non-empty strings")
    memory = requirements.get("memory_limit_mb")
    if memory is not None and (isinstance(memory, bool) or not isinstance(memory, (int, float)) or not math.isfinite(memory) or memory <= 0):
        raise ValueError("task_profile.requirements.memory_limit_mb must be a positive finite number")
    native_allowed = requirements.get("native_dependencies_allowed")
    if native_allowed is not None and not isinstance(native_allowed, bool):
        raise ValueError("task_profile.requirements.native_dependencies_allowed must be boolean")
    for field in ("priorities", "team_experience", "unknowns"):
        values = task.get(field, [])
        if not isinstance(values, list) or any(not isinstance(value, str) or not value.strip() for value in values):
            raise ValueError(f"task_profile.{field} must be a list of non-empty strings")


def _capability_result(stack: dict[str, Any], key: str) -> tuple[str, dict[str, Any] | None]:
    claim = stack.get("capabilities", {}).get(key)
    if not isinstance(claim, dict):
        return "unknown", None
    status = claim.get("status", "unknown")
    if status not in {"supported", "supported_with_conditions", "unsupported", "unknown"}:
        return "unknown", None
    return status, claim


def _hard_constraints(task: dict[str, Any], stack: dict[str, Any]) -> dict[str, list[str]]:
    result = {"passed": [], "failed": [], "unknown": []}
    checks: list[tuple[str, str]] = []
    target = task.get("target", {})
    if target.get("platform"):
        checks.append((f"target.platform={target['platform']}", f"platform.{_norm(target['platform'])}"))
    if target.get("deployment"):
        checks.append((f"target.deployment={target['deployment']}", f"deployment.{_norm(target['deployment'])}"))
    for integration in task.get("requirements", {}).get("required_integrations", []):
        checks.append((f"integration.{_norm(integration)}", f"integration.{_norm(integration)}"))

    requirements = task.get("requirements", {})
    if requirements.get("memory_limit_mb") is not None:
        key = "resources.memory_peak_mb"
        status, claim = _capability_result(stack, key)
        value = claim.get("value") if claim else None
        label = f"requirements.memory_limit_mb<={requirements['memory_limit_mb']}"
        if status == "supported" and isinstance(value, (int, float)):
            (result["passed"] if value <= requirements["memory_limit_mb"] else result["failed"]).append(label)
        else:
            result["unknown"].append(label)

    if requirements.get("native_dependencies_allowed") is False:
        key = "dependencies.native"
        status, claim = _capability_result(stack, key)
        value = claim.get("value") if claim else None
        label = "requirements.native_dependencies_allowed=false"
        if status == "supported" and value == "not_required":
            result["passed"].append(label)
        elif status == "supported" and value == "required":
            result["failed"].append(label)
        else:
            result["unknown"].append(label)

    for label, key in checks:
        status, _ = _capability_result(stack, key)
        if status == "supported":
            result["passed"].append(label)
        elif status == "unsupported":
            result["failed"].append(label)
        else:
            result["unknown"].append(label)
    return result


def _rank(task: dict[str, Any], stack: dict[str, Any]) -> tuple[int, list[str]]:
    score = 0
    reasons: list[str] = []
    existing = task.get("existing_project", {})
    languages = {_norm(value) for value in existing.get("languages", [])}
    frameworks = {_norm(value) for value in existing.get("frameworks", [])}
    stack_language = {_norm(stack.get("language_id", "")), _norm(stack.get("language_name", ""))}
    stack_frameworks = stack.get("frameworks", [stack.get("framework", "")])
    stack_framework = {_norm(value) for value in stack_frameworks if isinstance(value, str)}
    stack_framework.add(_norm(stack.get("id", "")))
    if languages & stack_language:
        score += RANK_WEIGHTS["existing_language"]
        reasons.append("Matches an existing project language (+100).")
    if frameworks & stack_framework:
        score += RANK_WEIGHTS["existing_framework"]
        reasons.append("Matches a framework already used by the project (+60).")

    experience = {_norm(value) for value in task.get("team_experience", [])}
    if experience & (stack_language | stack_framework):
        score += RANK_WEIGHTS["team_experience"]
        reasons.append("Matches recorded team experience (+20).")

    signals = stack.get("preference_signals", {})
    priorities = task.get("priorities", [])
    for index, priority in enumerate(priorities):
        weight = min((len(priorities) - index) * RANK_WEIGHTS["priority_step"], RANK_WEIGHTS["priority_cap"])
        signal = signals.get(priority) if isinstance(signals, dict) else None
        if isinstance(signal, dict) and signal.get("status") == "supported" and signal.get("evidence"):
            score += weight
            reasons.append(f"Evidence supports priority '{priority}' (+{weight}).")
    return score, reasons


def _supported_signal(signal: Any) -> bool:
    return (isinstance(signal, dict) and signal.get("status") == "supported"
            and bool(signal.get("evidence")))


def _record(task: dict[str, Any], stack: dict[str, Any]) -> dict[str, Any]:
    constraints = _hard_constraints(task, stack)
    score, reasons = _rank(task, stack)
    capabilities = stack.get("capabilities", {})
    signals = stack.get("preference_signals", {})
    evidence = [
        {"kind": "capability", "capability": key, **claim}
        for key, claim in sorted(capabilities.items())
        if isinstance(claim, dict) and claim.get("evidence")
    ]
    for priority, signal in sorted(signals.items()):
        if isinstance(signal, dict) and signal.get("evidence"):
            evidence.append({
                "kind": "preference_signal",
                "priority": priority,
                "status": signal.get("status", "unknown"),
                "conditions": signal.get("conditions", []),
                "evidence": signal["evidence"],
            })
    unknown_preferences = [
        priority for priority in task.get("priorities", [])
        if not _supported_signal(signals.get(priority))
    ]
    if unknown_preferences:
        reasons.append("No profile evidence ranks these priorities: " + ", ".join(unknown_preferences) + ".")
    if not reasons:
        reasons.append("No evidence-backed preference distinguishes this candidate.")
    reasons.extend(stack.get("reasons", []))
    return {
        "candidate": {
            "stack_id": stack["id"],
            "language_id": stack["language_id"],
            "language": stack["language_name"],
            "framework": stack.get("framework"),
            "runtime": stack.get("runtime"),
        },
        "hard_constraints": constraints,
        "rank_score": score,
        "rank_score_note": "Relative comparison points, not a probability of success.",
        "reasons": reasons,
        "tradeoffs": stack.get("tradeoffs", []),
        "evidence": evidence,
        "verification_status": stack.get("verification_status", "catalogue_only"),
        "open_questions": task.get("unknowns", []),
        "next_validation": stack.get("next_validation", "Build and test a minimal representative project."),
    }


def _assign_ranks(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    previous_score: int | None = None
    current_rank = 0
    for index, row in enumerate(rows, start=1):
        if row["rank_score"] != previous_score:
            current_rank = index
            previous_score = row["rank_score"]
        row["rank"] = current_rank
    return rows



def recommend_stack(task_profile: dict[str, Any], profiles: dict[str, Any], limit: int = 5) -> list[dict[str, Any]]:
    _validate_task(task_profile)
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= MAX_RESULTS:
        raise ValueError(f"limit must be an integer from 1 to {MAX_RESULTS}")
    ranked = []
    for stack in _profiles(profiles):
        record = _record(task_profile, stack)
        if record["hard_constraints"]["failed"]:
            continue
        ranked.append(record)
    ranked.sort(key=lambda row: -row["rank_score"])
    return _assign_ranks(ranked[:limit])


def compare_candidates(candidate_ids: list[str], task_profile: dict[str, Any], profiles: dict[str, Any]) -> list[dict[str, Any]]:
    if not isinstance(candidate_ids, list) or not candidate_ids or any(not isinstance(value, str) for value in candidate_ids):
        raise ValueError("candidate_ids must be a non-empty list of stack IDs")
    stacks = _profiles(profiles)
    by_id = {stack["id"]: stack for stack in stacks}
    if len(set(candidate_ids)) != len(candidate_ids):
        raise ValueError("candidate_ids must not contain duplicates")
    missing = sorted(set(candidate_ids) - set(by_id))
    if missing:
        raise ValueError("unknown candidate stack IDs: " + ", ".join(missing))
    _validate_task(task_profile)
    compared = [_record(task_profile, by_id[value]) for value in candidate_ids]
    compared.sort(key=lambda row: -row["rank_score"])
    return _assign_ranks(compared)


def get_suitability_evidence(language_id: str, capability: str | None, profiles: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(language_id, str) or not language_id:
        raise ValueError("language_id is required")
    stacks = _profiles(profiles)
    matches = [stack for stack in stacks if stack.get("language_id") == language_id]
    if not matches:
        raise ValueError(f"unknown language ID: {language_id}")
    if capability is not None and (not isinstance(capability, str) or not capability.strip()):
        raise ValueError("capability must be a non-empty string")
    claims = []
    for stack in matches:
        capabilities = stack.get("capabilities", {})
        selected = {capability: capabilities.get(capability)} if capability else capabilities
        for key, claim in sorted(selected.items()):
            if isinstance(claim, dict):
                claims.append({"stack_id": stack["id"], "capability": key, **claim})
            else:
                claims.append({"stack_id": stack["id"], "capability": key, "status": "unknown", "evidence": []})
    return {"language_id": language_id, "capability": capability, "claims": claims}
