import os
import json
from typing import Dict, Any, Optional, List, Union
from core.config.settings import settings
from core.interfaces.storage import IArtifactStorage
from modules.knowledge_base.storage.exceptions import (
    ArtifactNotFoundError,
    StorageConfigurationError,
    StorageError,
)

class LocalArtifactStorage(IArtifactStorage):
    """Local filesystem implementation of IArtifactStorage."""

    def __init__(self, base_dir: Optional[str] = None):
        target_dir = base_dir or settings.kb_storage.kb_raw_artifact_dir
        if not target_dir or not isinstance(target_dir, str):
            raise StorageConfigurationError("Invalid base directory for local artifact storage.")

        self.base_dir = os.path.abspath(target_dir)
        try:
            os.makedirs(self.base_dir, exist_ok=True)
        except Exception as e:
            raise StorageError(f"Failed to create artifact directory at {self.base_dir}: {str(e)}")

    def _get_content_path(self, artifact_id: str) -> str:
        safe_id = os.path.basename(artifact_id)
        return os.path.join(self.base_dir, f"{safe_id}.bin")

    def _get_meta_path(self, artifact_id: str) -> str:
        safe_id = os.path.basename(artifact_id)
        return os.path.join(self.base_dir, f"{safe_id}.meta.json")

    def save_artifact(
        self,
        artifact_id: str,
        content: Union[bytes, str],
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        if not artifact_id or not artifact_id.strip():
            raise StorageError("Artifact ID cannot be empty.")

        content_bytes = content.encode("utf-8") if isinstance(content, str) else content
        content_path = self._get_content_path(artifact_id)
        meta_path = self._get_meta_path(artifact_id)

        try:
            with open(content_path, "wb") as f:
                f.write(content_bytes)

            meta_data = metadata.copy() if metadata else {}
            meta_data["artifact_id"] = artifact_id
            meta_data["size_bytes"] = len(content_bytes)

            with open(meta_path, "w", encoding="utf-8") as f:
                json.dump(meta_data, f, indent=2)

            return artifact_id
        except Exception as e:
            raise StorageError(f"Failed to save artifact '{artifact_id}': {str(e)}")

    def get_artifact(self, artifact_id: str) -> bytes:
        if not self.has_artifact(artifact_id):
            raise ArtifactNotFoundError(f"Artifact '{artifact_id}' not found in local storage.")

        content_path = self._get_content_path(artifact_id)
        try:
            with open(content_path, "rb") as f:
                return f.read()
        except Exception as e:
            raise StorageError(f"Error reading artifact '{artifact_id}': {str(e)}")

    def get_artifact_metadata(self, artifact_id: str) -> Optional[Dict[str, Any]]:
        meta_path = self._get_meta_path(artifact_id)
        if not os.path.exists(meta_path):
            return None
        try:
            with open(meta_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            raise StorageError(f"Error reading metadata for artifact '{artifact_id}': {str(e)}")

    def has_artifact(self, artifact_id: str) -> bool:
        content_path = self._get_content_path(artifact_id)
        return os.path.exists(content_path)

    def delete_artifact(self, artifact_id: str) -> bool:
        if not self.has_artifact(artifact_id):
            raise ArtifactNotFoundError(f"Cannot delete. Artifact '{artifact_id}' not found.")

        content_path = self._get_content_path(artifact_id)
        meta_path = self._get_meta_path(artifact_id)

        try:
            if os.path.exists(content_path):
                os.remove(content_path)
            if os.path.exists(meta_path):
                os.remove(meta_path)
            return True
        except Exception as e:
            raise StorageError(f"Failed to delete artifact '{artifact_id}': {str(e)}")

    def list_artifacts(self) -> List[str]:
        try:
            artifacts = []
            for fname in os.listdir(self.base_dir):
                if fname.endswith(".bin"):
                    artifact_id = fname[:-4]
                    artifacts.append(artifact_id)
            return sorted(artifacts)
        except Exception as e:
            raise StorageError(f"Failed to list artifacts: {str(e)}")
