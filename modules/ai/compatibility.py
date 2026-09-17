"""Model Compatibility Validation and Validation Gate for EarthMind AI Layer."""

from datetime import datetime, timezone
from typing import Dict, Any, Optional, List
from core.schemas.model import ModelVersionRecord, ValidationResult, ModelLifecycleState
from core.errors.exceptions import (
    ModelCompatibilityError,
    InvalidRevisionError,
    ValidationGateError
)
from core.logging.logger import get_logger

logger = get_logger("modules.ai.compatibility")


class ModelCompatibilityChecker:
    """Validates compatibility between a candidate model version and EarthMind runtime requirements.

    Performs lightweight metadata and configuration checks without loading weights or downloading artifacts.
    """

    SUPPORTED_PROVIDERS = {"huggingface", "local", "vllm", "onnx"}
    SUPPORTED_MODEL_TYPES = {"causal_lm", "seq2seq", "transformer", "vision_language", "audio_lm"}
    SUPPORTED_EXECUTION_STRATEGIES = {"causal_lm_adapter", "vision_adapter", "audio_adapter", "generic_adapter"}

    def check_compatibility(self, record: ModelVersionRecord) -> Dict[str, Any]:
        """Perform comprehensive metadata and configuration compatibility checks.

        Returns a dictionary with status and list of performed check details.
        Raises ModelCompatibilityError or InvalidRevisionError if critical validation fails.
        """
        checks: List[Dict[str, Any]] = []

        # Check 1: Identifier check
        if not record.identifier or not record.identifier.strip():
            raise ModelCompatibilityError(
                getattr(record, "identifier", "unknown"),
                record.version,
                "Model identifier cannot be empty."
            )
        checks.append({"check": "identifier_validation", "passed": True, "details": f"Identifier: {record.identifier}"})

        # Check 2: Repository ID format check
        if not record.repo_id or "/" not in record.repo_id:
            raise ModelCompatibilityError(
                record.identifier,
                record.version,
                f"Invalid repo_id '{record.repo_id}'. Must be in 'owner/repo' format."
            )
        checks.append({"check": "repo_id_validation", "passed": True, "details": f"Repo ID: {record.repo_id}"})

        # Check 3: Pinned Revision check
        rev = record.revision.strip() if record.revision else ""
        if not rev or len(rev) < 8 or not rev.isalnum():
            raise InvalidRevisionError(
                record.identifier,
                record.revision,
                "Revision must be a valid pinned commit SHA of at least 8 alphanumeric characters."
            )
        checks.append({"check": "revision_pinning_validation", "passed": True, "details": f"Revision SHA: {rev}"})

        # Check 4: Provider check
        if record.provider.lower() not in self.SUPPORTED_PROVIDERS:
            raise ModelCompatibilityError(
                record.identifier,
                record.version,
                f"Unsupported provider '{record.provider}'. Supported: {sorted(list(self.SUPPORTED_PROVIDERS))}"
            )
        checks.append({"check": "provider_validation", "passed": True, "details": f"Provider: {record.provider}"})

        # Check 5: Model Type / Architecture check
        if record.model_type.lower() not in self.SUPPORTED_MODEL_TYPES:
            raise ModelCompatibilityError(
                record.identifier,
                record.version,
                f"Unsupported model_type '{record.model_type}'. Supported: {sorted(list(self.SUPPORTED_MODEL_TYPES))}"
            )
        checks.append({"check": "model_type_validation", "passed": True, "details": f"Model Type: {record.model_type}"})

        # Check 6: Execution Strategy check
        if record.execution_strategy and record.execution_strategy.lower() not in self.SUPPORTED_EXECUTION_STRATEGIES:
            raise ModelCompatibilityError(
                record.identifier,
                record.version,
                f"Unsupported execution strategy '{record.execution_strategy}'."
            )
        checks.append({"check": "execution_strategy_validation", "passed": True, "details": f"Strategy: {record.execution_strategy}"})

        logger.info(f"Compatibility checks PASSED for model '{record.identifier}' (v{record.version}, revision={record.revision[:8]})")
        return {"is_compatible": True, "checks": checks}


class ValidationGate:
    """Validation Gate enforcing safety before candidate model versions reach STAGED or ACTIVE states."""

    def __init__(self, checker: Optional[ModelCompatibilityChecker] = None):
        self._checker = checker or ModelCompatibilityChecker()

    def validate(self, record: ModelVersionRecord, extra_checks: Optional[List[Dict[str, Any]]] = None) -> ValidationResult:
        """Execute validation gate checks against a candidate ModelVersionRecord.

        Returns a structured ValidationResult object.
        """
        now_str = datetime.now(timezone.utc).isoformat()
        all_checks: List[Dict[str, Any]] = []
        errors: List[str] = []

        logger.info(f"Validation Gate started for candidate model '{record.identifier}' (v{record.version})...")

        # Compatibility check
        try:
            compat_res = self._checker.check_compatibility(record)
            all_checks.extend(compat_res.get("checks", []))
        except (ModelCompatibilityError, InvalidRevisionError) as e:
            errors.append(str(e))
            logger.error(f"Validation Gate compatibility check failed for '{record.identifier}' (v{record.version}): {e}")

        # Extra metadata validation checks if provided
        if extra_checks:
            for check in extra_checks:
                check_name = check.get("name", "custom_check")
                passed = check.get("passed", False)
                details = check.get("details", "")
                all_checks.append({"check": check_name, "passed": passed, "details": details})
                if not passed:
                    err_msg = f"Check '{check_name}' failed: {details}"
                    errors.append(err_msg)
                    logger.warning(f"Validation Gate custom check failed for '{record.identifier}': {err_msg}")

        is_valid = len(errors) == 0
        status_str = "PASSED" if is_valid else "FAILED"
        logger.info(f"Validation Gate finished for '{record.identifier}' (v{record.version}) with status: {status_str}")

        return ValidationResult(
            is_valid=is_valid,
            checks=all_checks,
            errors=errors,
            timestamp=now_str,
            metadata={
                "identifier": record.identifier,
                "version": record.version,
                "repo_id": record.repo_id,
                "revision": record.revision,
                "validation_status": status_str
            }
        )
