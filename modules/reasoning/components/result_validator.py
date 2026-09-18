from modules.reasoning.errors import InvalidReasoningResultError
from modules.reasoning.schemas import ReasoningResult


class ResultValidator:
    """Validates ReasoningResult structure and Rule compliance before Inspector handoff."""

    def validate_result(self, result: ReasoningResult) -> None:
        if not result or not result.request_id:
            raise InvalidReasoningResultError("unknown", "ReasoningResult must have valid request_id.")

        # Rule 1 Check: Findings must reference evidence IDs or explicit assumptions
        for finding in result.findings:
            if not finding.evidence_ids and not finding.assumption_ids and not result.assumptions:
                raise InvalidReasoningResultError(
                    result.request_id,
                    f"Finding '{finding.finding_id}' violates Core Rule 1 (Evidence Before Conclusion): No evidence IDs or explicit assumptions linked."
                )

        # Rule 3 Check: Conflicting evidence must remain represented if present
        for conflict in result.conflicts:
            if not conflict.evidence_ids or len(conflict.evidence_ids) < 2:
                raise InvalidReasoningResultError(
                    result.request_id,
                    f"Conflict '{conflict.conflict_id}' must reference at least two conflicting evidence items."
                )
