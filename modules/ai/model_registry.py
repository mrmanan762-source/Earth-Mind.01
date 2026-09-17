"""EarthMind AI Module: ModelRegistry component supporting multi-version model management, lifecycle state transitions, staging, activation, rollback, deprecation, and retirement."""

from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
from core.config.settings import ModelConfig, settings
from core.schemas.model import ModelVersionRecord, ModelLifecycleState, ValidationResult
from core.errors.exceptions import (
    EarthMindException,
    UnknownModelVersionError,
    InvalidLifecycleTransitionError,
    ModelCompatibilityError,
    ValidationGateError,
    ModelActivationError,
    ModelRollbackError,
    RetiredModelSelectedError,
    ConflictingActiveVersionError,
    InvalidRevisionError
)
from modules.ai.compatibility import ModelCompatibilityChecker, ValidationGate
from core.logging.logger import get_logger

logger = get_logger("modules.ai.model_registry")


class ModelNotFoundError(EarthMindException):
    def __init__(self, identifier: str):
        super().__init__(
            message=f"Model identifier '{identifier}' is not registered in ModelRegistry.",
            error_code="MODEL_NOT_FOUND",
            module="ai",
            operation="registry_resolve"
        )


class InvalidModelConfigError(EarthMindException):
    def __init__(self, identifier: str, details: str):
        super().__init__(
            message=f"Invalid configuration for model '{identifier}': {details}",
            error_code="INVALID_MODEL_CONFIG",
            module="ai",
            operation="registry_validate"
        )


class ModelRegistry:
    """Central registry managing EarthMind model configurations, versions, lifecycle transitions, and traceability."""

    # Allowed state transitions: source_state -> set of valid target_states
    VALID_TRANSITIONS = {
        ModelLifecycleState.REGISTERED: {ModelLifecycleState.VALIDATING, ModelLifecycleState.STAGED, ModelLifecycleState.DEPRECATED, ModelLifecycleState.RETIRED},
        ModelLifecycleState.VALIDATING: {ModelLifecycleState.STAGED, ModelLifecycleState.REGISTERED, ModelLifecycleState.DEPRECATED, ModelLifecycleState.RETIRED},
        ModelLifecycleState.STAGED: {ModelLifecycleState.ACTIVE, ModelLifecycleState.VALIDATING, ModelLifecycleState.DEPRECATED, ModelLifecycleState.RETIRED},
        ModelLifecycleState.ACTIVE: {ModelLifecycleState.DEPRECATED, ModelLifecycleState.RETIRED, ModelLifecycleState.STAGED},
        ModelLifecycleState.DEPRECATED: {ModelLifecycleState.ACTIVE, ModelLifecycleState.STAGED, ModelLifecycleState.RETIRED},
        ModelLifecycleState.RETIRED: set()  # Retired models cannot transition directly to active/staged without re-registration
    }

    def __init__(self, register_defaults: bool = True):
        self._models: Dict[str, ModelConfig] = {}
        self._versions: Dict[str, Dict[str, ModelVersionRecord]] = {}
        self._active_versions: Dict[str, str] = {}
        self._previous_active_versions: Dict[str, str] = {}
        self._audit_log: List[Dict[str, Any]] = []

        self._gate = ValidationGate()

        if register_defaults:
            self._register_default_sarvam()

    def _record_audit_event(
        self,
        operation: str,
        identifier: str,
        version: str,
        repo_id: str,
        revision: str,
        lifecycle_state: str,
        previous_version: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ) -> None:
        event = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "operation": operation,
            "identifier": identifier,
            "version": version,
            "repo_id": repo_id,
            "revision": revision,
            "lifecycle_state": lifecycle_state,
            "previous_version": previous_version,
            "details": details or {}
        }
        self._audit_log.append(event)
        logger.info(f"[AUDIT] {operation.upper()} | Model: {identifier} (v{version}) | State: {lifecycle_state} | Revision: {revision[:8] if revision else 'N/A'}")

    def _register_default_sarvam(self) -> None:
        main_cfg = settings.main_model
        now_str = datetime.now(timezone.utc).isoformat()
        record = ModelVersionRecord(
            identifier=main_cfg.identifier,
            version=main_cfg.version,
            family=main_cfg.family,
            provider=main_cfg.provider,
            repo_id=main_cfg.repo_id,
            revision=main_cfg.revision,
            model_type=main_cfg.model_type,
            license=main_cfg.license,
            provenance=main_cfg.provenance,
            state=ModelLifecycleState.ACTIVE,
            registration_timestamp=now_str,
            is_main_model=True
        )
        if record.identifier not in self._versions:
            self._versions[record.identifier] = {}

        self._versions[record.identifier][record.version] = record
        self._active_versions[record.identifier] = record.version
        self._models[record.identifier] = main_cfg

        self._record_audit_event(
            operation="default_registered",
            identifier=record.identifier,
            version=record.version,
            repo_id=record.repo_id,
            revision=record.revision,
            lifecycle_state=ModelLifecycleState.ACTIVE.value,
            details={"is_main_model": True}
        )

    def register_version(self, record: ModelVersionRecord) -> ModelVersionRecord:
        """Register a new ModelVersionRecord into the registry."""
        if not record.identifier or not record.identifier.strip():
            raise InvalidModelConfigError("unknown", "Model identifier cannot be empty.")

        # Check repo_id and revision basic validity
        if not record.repo_id or "/" not in record.repo_id:
            raise InvalidModelConfigError(record.identifier, f"Invalid repo_id '{record.repo_id}'. Must be 'owner/repo'.")

        if not record.revision or len(record.revision.strip()) < 8:
            raise InvalidRevisionError(record.identifier, record.revision, "Revision must be a valid pinned SHA of at least 8 chars.")

        ident = record.identifier
        ver = record.version

        if ident not in self._versions:
            self._versions[ident] = {}

        # Store version record
        self._versions[ident][ver] = record

        # If this is marked as ACTIVE on registration (and no active exists), track it
        if record.state == ModelLifecycleState.ACTIVE:
            if ident not in self._active_versions:
                self._active_versions[ident] = ver

        # Update _models dict for backward compatibility
        self._models[ident] = ModelConfig(
            identifier=record.identifier,
            version=record.version,
            family=record.family,
            provider=record.provider,
            repo_id=record.repo_id,
            revision=record.revision,
            model_type=record.model_type,
            license=record.license,
            provenance=record.provenance,
            is_main_model=record.is_main_model,
            lifecycle_state=record.state.value,
            metadata=record.metadata
        )

        self._record_audit_event(
            operation="version_registered",
            identifier=ident,
            version=ver,
            repo_id=record.repo_id,
            revision=record.revision,
            lifecycle_state=record.state.value
        )
        return record

    def register_model(self, config: ModelConfig) -> None:
        """Register or update a ModelConfig in the registry after validation (backward compatible)."""
        try:
            config.validate_config()
        except ValueError as e:
            raise InvalidModelConfigError(config.identifier, str(e)) from e

        now_str = datetime.now(timezone.utc).isoformat()
        try:
            state_enum = ModelLifecycleState(config.lifecycle_state)
        except ValueError:
            state_enum = ModelLifecycleState.ACTIVE if config.is_main_model else ModelLifecycleState.REGISTERED

        record = ModelVersionRecord(
            identifier=config.identifier,
            version=config.version,
            family=config.family,
            provider=config.provider,
            repo_id=config.repo_id,
            revision=config.revision,
            model_type=config.model_type,
            license=config.license,
            provenance=config.provenance,
            state=state_enum,
            registration_timestamp=now_str,
            metadata=config.metadata,
            is_main_model=config.is_main_model
        )

        self.register_version(record)

    def get_version(self, identifier: str, version: str) -> ModelVersionRecord:
        """Retrieve explicit ModelVersionRecord by identifier and version."""
        if identifier not in self._versions or version not in self._versions[identifier]:
            raise UnknownModelVersionError(identifier, version)
        return self._versions[identifier][version]

    def version_exists(self, identifier: str, version: str) -> bool:
        """Check if a specific model version is registered."""
        return identifier in self._versions and version in self._versions[identifier]

    def get_model(self, identifier: str) -> ModelConfig:
        """Resolve and return a registered ModelConfig by its identifier."""
        if identifier in self._models:
            return self._models[identifier]
        if identifier in self._versions and self._versions[identifier]:
            # Return active version config if available
            active_ver = self._active_versions.get(identifier)
            if active_ver and active_ver in self._versions[identifier]:
                rec = self._versions[identifier][active_ver]
            else:
                rec = list(self._versions[identifier].values())[-1]

            return ModelConfig(
                identifier=rec.identifier,
                version=rec.version,
                family=rec.family,
                provider=rec.provider,
                repo_id=rec.repo_id,
                revision=rec.revision,
                model_type=rec.model_type,
                license=rec.license,
                provenance=rec.provenance,
                is_main_model=rec.is_main_model,
                lifecycle_state=rec.state.value,
                metadata=rec.metadata
            )
        raise ModelNotFoundError(identifier)

    def get_main_model(self) -> ModelConfig:
        """Resolve the primary/main EarthMind model configuration."""
        for ident, recs in self._versions.items():
            for rec in recs.values():
                if rec.is_main_model and rec.state == ModelLifecycleState.ACTIVE:
                    return ModelConfig(
                        identifier=rec.identifier,
                        version=rec.version,
                        family=rec.family,
                        provider=rec.provider,
                        repo_id=rec.repo_id,
                        revision=rec.revision,
                        model_type=rec.model_type,
                        license=rec.license,
                        provenance=rec.provenance,
                        is_main_model=rec.is_main_model,
                        lifecycle_state=rec.state.value,
                        metadata=rec.metadata
                    )

        for config in self._models.values():
            if config.is_main_model:
                return config

        return settings.main_model

    def list_models(self) -> List[str]:
        """Return a list of registered model identifiers."""
        keys = list(self._models.keys())
        for k in self._versions.keys():
            if k not in keys:
                keys.append(k)
        return keys

    def list_versions(self, identifier: Optional[str] = None) -> List[ModelVersionRecord]:
        """List all version records, optionally filtered by model identifier."""
        results: List[ModelVersionRecord] = []
        if identifier:
            if identifier in self._versions:
                results.extend(list(self._versions[identifier].values()))
        else:
            for recs in self._versions.values():
                results.extend(list(recs.values()))
        return results

    def is_registered(self, identifier: str) -> bool:
        """Check if a model identifier is registered."""
        return identifier in self._models or (identifier in self._versions and len(self._versions[identifier]) > 0)

    def get_active_version(self, identifier: str = "sarvam-105b") -> ModelVersionRecord:
        """Get the currently ACTIVE ModelVersionRecord for an identifier."""
        active_ver = self._active_versions.get(identifier)
        if not active_ver or identifier not in self._versions or active_ver not in self._versions[identifier]:
            raise ModelNotFoundError(f"No active version found for model '{identifier}'.")
        record = self._versions[identifier][active_ver]
        if record.state == ModelLifecycleState.RETIRED:
            raise RetiredModelSelectedError(identifier, active_ver)
        return record

    def select_version(
        self,
        identifier: str,
        version: Optional[str] = None,
        allow_fallback: bool = True
    ) -> ModelVersionRecord:
        """Select a model version by explicit version tag or active version fallback."""
        if version:
            if not self.version_exists(identifier, version):
                raise UnknownModelVersionError(identifier, version)
            record = self.get_version(identifier, version)
            if record.state == ModelLifecycleState.RETIRED:
                raise RetiredModelSelectedError(identifier, version)
            return record

        # Return active version
        if identifier in self._active_versions:
            active_ver = self._active_versions[identifier]
            if active_ver in self._versions[identifier]:
                record = self._versions[identifier][active_ver]
                if record.state != ModelLifecycleState.RETIRED:
                    return record

        if allow_fallback and identifier in self._versions and self._versions[identifier]:
            for rec in reversed(list(self._versions[identifier].values())):
                if rec.state != ModelLifecycleState.RETIRED:
                    return rec

        raise ModelNotFoundError(f"No active or valid fallback version available for model '{identifier}'.")

    def update_lifecycle_state(
        self,
        identifier: str,
        version: str,
        target_state: ModelLifecycleState,
        reason: str = ""
    ) -> ModelVersionRecord:
        """Transition model version lifecycle state safely."""
        record = self.get_version(identifier, version)
        current_state = record.state

        if current_state == target_state:
            return record

        # Rule check: RETIRED models cannot transition directly to ACTIVE without re-registration
        if current_state == ModelLifecycleState.RETIRED and target_state in (ModelLifecycleState.ACTIVE, ModelLifecycleState.STAGED):
            raise InvalidLifecycleTransitionError(
                identifier,
                version,
                current_state.value,
                target_state.value,
                "Retired models cannot transition directly to ACTIVE or STAGED. Register a new version record."
            )

        valid_targets = self.VALID_TRANSITIONS.get(current_state, set())
        if target_state not in valid_targets and target_state != current_state:
            raise InvalidLifecycleTransitionError(
                identifier,
                version,
                current_state.value,
                target_state.value,
                reason or "Transition not allowed by lifecycle rules."
            )

        # Update record
        updated_record = record.model_copy(update={"state": target_state})
        self._versions[identifier][version] = updated_record

        self._record_audit_event(
            operation="lifecycle_transition",
            identifier=identifier,
            version=version,
            repo_id=record.repo_id,
            revision=record.revision,
            lifecycle_state=target_state.value,
            details={"previous_state": current_state.value, "reason": reason}
        )
        return updated_record

    def validate_version(
        self,
        identifier: str,
        version: str,
        extra_checks: Optional[List[Dict[str, Any]]] = None
    ) -> ValidationResult:
        """Run candidate version through Validation Gate."""
        record = self.get_version(identifier, version)

        # Transition state to VALIDATING if REGISTERED
        if record.state == ModelLifecycleState.REGISTERED:
            record = self.update_lifecycle_state(identifier, version, ModelLifecycleState.VALIDATING, "Validation started")

        self._record_audit_event(
            operation="validation_started",
            identifier=identifier,
            version=version,
            repo_id=record.repo_id,
            revision=record.revision,
            lifecycle_state=record.state.value
        )

        res = self._gate.validate(record, extra_checks=extra_checks)

        event_name = "validation_completed" if res.is_valid else "validation_failed"
        self._record_audit_event(
            operation=event_name,
            identifier=identifier,
            version=version,
            repo_id=record.repo_id,
            revision=record.revision,
            lifecycle_state=record.state.value,
            details={"is_valid": res.is_valid, "errors": res.errors}
        )
        return res

    def stage_version(
        self,
        identifier: str,
        version: str,
        validation_result: Optional[ValidationResult] = None
    ) -> ModelVersionRecord:
        """Transition candidate version to STAGED state without automatically replacing active version."""
        record = self.get_version(identifier, version)

        if record.state == ModelLifecycleState.STAGED:
            return record

        if record.state == ModelLifecycleState.RETIRED:
            raise InvalidLifecycleTransitionError(identifier, version, record.state.value, ModelLifecycleState.STAGED.value, "Cannot stage retired model.")

        if not validation_result:
            validation_result = self.validate_version(identifier, version)

        if not validation_result.is_valid:
            raise ValidationGateError(identifier, version, f"Validation failed: {', '.join(validation_result.errors)}")

        staged_record = self.update_lifecycle_state(
            identifier=identifier,
            version=version,
            target_state=ModelLifecycleState.STAGED,
            reason="Validation passed successfully."
        )

        self._record_audit_event(
            operation="staged",
            identifier=identifier,
            version=version,
            repo_id=record.repo_id,
            revision=record.revision,
            lifecycle_state=ModelLifecycleState.STAGED.value
        )
        return staged_record

    def activate_version(
        self,
        identifier: str,
        version: str,
        force: bool = False
    ) -> ModelVersionRecord:
        """Atomically activate a model version, preserving previous active version as rollback candidate."""
        record = self.get_version(identifier, version)

        if record.state == ModelLifecycleState.RETIRED:
            raise RetiredModelSelectedError(identifier, version)

        # Ensure candidate is validated and staged unless forced
        if not force and record.state not in (ModelLifecycleState.STAGED, ModelLifecycleState.ACTIVE):
            val_res = self.validate_version(identifier, version)
            if not val_res.is_valid:
                raise ModelActivationError(identifier, version, f"Validation gate failed: {', '.join(val_res.errors)}")
            record = self.stage_version(identifier, version, val_res)

        current_active_version = self._active_versions.get(identifier)

        # If already active, return
        if current_active_version == version and record.state == ModelLifecycleState.ACTIVE:
            return record

        # Preserve previous active version
        if current_active_version and current_active_version != version:
            if current_active_version in self._versions[identifier]:
                prev_record = self._versions[identifier][current_active_version]
                if prev_record.state == ModelLifecycleState.ACTIVE:
                    # Transition previous active to DEPRECATED
                    demoted_record = prev_record.model_copy(update={"state": ModelLifecycleState.DEPRECATED})
                    self._versions[identifier][current_active_version] = demoted_record

            self._previous_active_versions[identifier] = current_active_version

        # Set target version to ACTIVE
        active_record = record.model_copy(update={"state": ModelLifecycleState.ACTIVE})
        self._versions[identifier][version] = active_record
        self._active_versions[identifier] = version

        # Update _models dict for backward compatibility
        self._models[identifier] = ModelConfig(
            identifier=active_record.identifier,
            version=active_record.version,
            family=active_record.family,
            provider=active_record.provider,
            repo_id=active_record.repo_id,
            revision=active_record.revision,
            model_type=active_record.model_type,
            license=active_record.license,
            provenance=active_record.provenance,
            is_main_model=active_record.is_main_model,
            lifecycle_state=active_record.state.value,
            metadata=active_record.metadata
        )

        self._record_audit_event(
            operation="activated",
            identifier=identifier,
            version=version,
            repo_id=active_record.repo_id,
            revision=active_record.revision,
            lifecycle_state=ModelLifecycleState.ACTIVE.value,
            previous_version=current_active_version
        )
        return active_record

    def rollback_version(self, identifier: str) -> ModelVersionRecord:
        """Roll back active model to the previous valid active version."""
        previous_version = self._previous_active_versions.get(identifier)
        if not previous_version:
            # Fallback: check if there is a deprecated or staged version in history
            if identifier in self._versions:
                for ver, rec in reversed(list(self._versions[identifier].items())):
                    if ver != self._active_versions.get(identifier) and rec.state in (ModelLifecycleState.DEPRECATED, ModelLifecycleState.STAGED):
                        previous_version = ver
                        break

        if not previous_version or not self.version_exists(identifier, previous_version):
            raise ModelRollbackError(identifier, "No valid previous active version found to roll back to.")

        prev_record = self.get_version(identifier, previous_version)
        if prev_record.state == ModelLifecycleState.RETIRED:
            raise ModelRollbackError(identifier, f"Previous active version '{previous_version}' is RETIRED and cannot be restored.")

        current_active = self._active_versions.get(identifier)

        # Demote current active
        if current_active and current_active in self._versions[identifier]:
            curr_rec = self._versions[identifier][current_active]
            if curr_rec.state == ModelLifecycleState.ACTIVE:
                demoted = curr_rec.model_copy(update={"state": ModelLifecycleState.DEPRECATED})
                self._versions[identifier][current_active] = demoted

        # Promote previous active
        restored = prev_record.model_copy(update={"state": ModelLifecycleState.ACTIVE})
        self._versions[identifier][previous_version] = restored
        self._active_versions[identifier] = previous_version

        # Update _models dict
        self._models[identifier] = ModelConfig(
            identifier=restored.identifier,
            version=restored.version,
            family=restored.family,
            provider=restored.provider,
            repo_id=restored.repo_id,
            revision=restored.revision,
            model_type=restored.model_type,
            license=restored.license,
            provenance=restored.provenance,
            is_main_model=restored.is_main_model,
            lifecycle_state=restored.state.value,
            metadata=restored.metadata
        )

        self._record_audit_event(
            operation="rollback",
            identifier=identifier,
            version=previous_version,
            repo_id=restored.repo_id,
            revision=restored.revision,
            lifecycle_state=ModelLifecycleState.ACTIVE.value,
            previous_version=current_active
        )
        return restored

    def deprecate_version(self, identifier: str, version: str) -> ModelVersionRecord:
        """Mark a model version as DEPRECATED."""
        record = self.update_lifecycle_state(
            identifier=identifier,
            version=version,
            target_state=ModelLifecycleState.DEPRECATED,
            reason="Version marked as deprecated."
        )
        return record

    def retire_version(self, identifier: str, version: str) -> ModelVersionRecord:
        """Mark a model version as RETIRED, preventing future activation without deleting history."""
        record = self.get_version(identifier, version)

        retired_record = record.model_copy(update={"state": ModelLifecycleState.RETIRED})
        self._versions[identifier][version] = retired_record

        # If it was active, clear active pointer
        if self._active_versions.get(identifier) == version:
            del self._active_versions[identifier]

        self._record_audit_event(
            operation="retired",
            identifier=identifier,
            version=version,
            repo_id=record.repo_id,
            revision=record.revision,
            lifecycle_state=ModelLifecycleState.RETIRED.value
        )
        return retired_record

    def get_audit_log(self, identifier: Optional[str] = None) -> List[Dict[str, Any]]:
        """Retrieve recorded audit events."""
        if identifier:
            return [e for e in self._audit_log if e.get("identifier") == identifier]
        return list(self._audit_log)
