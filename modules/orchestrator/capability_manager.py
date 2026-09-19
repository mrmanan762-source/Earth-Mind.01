from typing import Any, Dict, List, Optional

from core.logging.logger import get_logger
from modules.orchestrator.enums import CapabilityStatus
from modules.orchestrator.errors import CapabilityNotFoundError, InvalidContractError
from modules.orchestrator.interfaces import ICapability, ICapabilityManager
from modules.orchestrator.schemas import CapabilityMetadata

logger = get_logger("orchestrator.capability_manager")


class CapabilityManager(ICapabilityManager):
    """B5.3 Capability Manager.

    Responsibilities:
    - Maintain registry of replaceable system capabilities.
    - Track capability metadata (id, version, operations, contracts, status).
    - Provide capability lookup and availability status checks.
    - Enforce contract compatibility checks for capability substitution.
    - Support interface-only capability invocation.
    """

    def __init__(self) -> None:
        self._capabilities: Dict[str, ICapability] = {}
        self._metadata_registry: Dict[str, CapabilityMetadata] = {}

    def register_capability(
        self, capability: ICapability, metadata: Optional[CapabilityMetadata] = None
    ) -> None:
        """Register a capability instance into the registry."""
        cap_id = capability.capability_id
        meta = metadata or (
            capability.get_metadata()
            if hasattr(capability, "get_metadata") and callable(capability.get_metadata)
            else CapabilityMetadata(
                capability_id=cap_id,
                version=getattr(capability, "version", "1.0.0"),
                interface_name=getattr(capability, "interface_name", type(capability).__name__),
            )
        )

        self._capabilities[cap_id] = capability
        self._metadata_registry[cap_id] = meta
        logger.info(
            f"Registered capability '{cap_id}' (v{meta.version}) in capability manager",
            extra={"capability_id": cap_id, "version": meta.version},
        )

    def unregister_capability(self, capability_id: str) -> None:
        """Unregister a capability from the registry."""
        if capability_id in self._capabilities:
            del self._capabilities[capability_id]
        if capability_id in self._metadata_registry:
            del self._metadata_registry[capability_id]
        logger.info(f"Unregistered capability '{capability_id}'")

    def get_capability(self, capability_id: str) -> ICapability:
        """Retrieve registered capability instance or raise CapabilityNotFoundError."""
        if capability_id not in self._capabilities:
            raise CapabilityNotFoundError(capability_id)
        return self._capabilities[capability_id]

    def get_metadata(self, capability_id: str) -> CapabilityMetadata:
        """Retrieve capability metadata or raise CapabilityNotFoundError."""
        if capability_id not in self._metadata_registry:
            raise CapabilityNotFoundError(capability_id)
        return self._metadata_registry[capability_id]

    def set_availability(self, capability_id: str, status: CapabilityStatus) -> None:
        """Update capability health / availability status."""
        meta = self.get_metadata(capability_id)
        meta.availability = status
        self._metadata_registry[capability_id] = meta

    def is_available(self, capability_id: str) -> bool:
        """Check if capability is registered and available."""
        if capability_id not in self._capabilities:
            return False
        meta = self._metadata_registry.get(capability_id)
        if not meta:
            return False
        return meta.availability in (CapabilityStatus.AVAILABLE, CapabilityStatus.REGISTERED, CapabilityStatus.DEGRADED)

    def check_contract_compatibility(
        self, source_capability_id: str, target_capability_id: str
    ) -> bool:
        """Verify contract compatibility for capability substitution.

        Target substitute capability must support required operations and compatible output contract.
        """
        source_meta = self.get_metadata(source_capability_id)
        target_meta = self.get_metadata(target_capability_id)

        # Ensure target capability is available
        if not self.is_available(target_capability_id):
            return False

        # Ensure target capability supports all required operations of source
        for op in source_meta.supported_operations:
            if op not in target_meta.supported_operations and target_meta.supported_operations:
                return False

        # If output contract schemas are defined, check key set compatibility
        if source_meta.output_contract and target_meta.output_contract:
            source_keys = set(source_meta.output_contract.keys())
            target_keys = set(target_meta.output_contract.keys())
            if not source_keys.issubset(target_keys):
                return False

        return True

    def validate_capability_contract(
        self, capability_id: str, operation: str, payload: Any
    ) -> None:
        """Validate input payload against capability input contract if defined."""
        meta = self.get_metadata(capability_id)
        if meta.supported_operations and operation not in meta.supported_operations:
            raise InvalidContractError(
                capability_id,
                f"Operation '{operation}' is not supported by capability '{capability_id}'"
            )
