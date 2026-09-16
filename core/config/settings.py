import os
from typing import Dict, Optional
from pydantic import BaseModel, Field

class ModelConfig(BaseModel):
    identifier: str = Field(..., description="Unique model identifier within EarthMind")
    provider: str = Field("huggingface", description="Model provider or host platform")
    repo_id: str = Field(..., description="Hugging Face repository ID")
    revision: str = Field(..., description="Exact pinned commit SHA or revision")
    model_type: str = Field("causal_lm", description="Architecture/type metadata")
    license: str = Field("Apache-2.0", description="Model license terms")
    provenance: str = Field("upstream: sarvamai/sarvam-105b", description="Model provenance information")
    is_main_model: bool = Field(False, description="Whether this is the primary EarthMind model")

    def validate_config(self) -> bool:
        if not self.identifier or not self.identifier.strip():
            raise ValueError("Model identifier cannot be empty.")
        if not self.repo_id or "/" not in self.repo_id:
            raise ValueError(f"Invalid repo_id '{self.repo_id}'. Must be in format 'owner/repo'.")
        if not self.revision or len(self.revision.strip()) < 8:
            raise ValueError(f"Invalid revision '{self.revision}'. Must be a valid pinned commit SHA.")
        return True

class ModelRuntimeConfig(BaseModel):
    execution_timeout: float = Field(30.0, description="Maximum allowed execution time in seconds for model requests")
    concurrency_limit: int = Field(5, description="Maximum concurrent execution requests allowed by runtime")
    runtime_mode: str = Field("mock", description="Runtime execution mode (e.g., 'mock', 'development', 'production')")
    resource_policy: str = Field("mock", description="Resource allocation policy (e.g., 'mock', 'strict')")

class ModelLoadingConfig(BaseModel):
    loading_strategy: str = Field("remote", description="Loading strategy ('remote', 'local', 'hybrid')")
    local_cache_dir: Optional[str] = Field(".cache/earthmind/models", description="Local directory for cached model artifacts")
    initialization_timeout: float = Field(60.0, description="Initialization timeout in seconds")
    resource_policy: str = Field("mock", description="Resource allocation policy for model loading")
    compatibility_policy: str = Field("strict", description="Compatibility verification policy ('strict', 'permissive')")

class Settings(BaseModel):
    app_name: str = "EarthMind"
    environment: str = os.getenv("EARTHMIND_ENV", "development")
    version: str = "0.1.0"
    db_path: str = os.getenv("EARTHMIND_DB_PATH", "earthmind.db")
    log_level: str = os.getenv("EARTHMIND_LOG_LEVEL", "INFO")
    main_model: ModelConfig = Field(
        default_factory=lambda: ModelConfig(
            identifier="sarvam-105b",
            provider="huggingface",
            repo_id=os.getenv("EARTHMIND_MAIN_MODEL_REPO", "mrmanan762/EarthMind"),
            revision=os.getenv("EARTHMIND_MAIN_MODEL_REVISION", "fb187764dbad56ed8b26742a802909e858e9bb72"),
            model_type="causal_lm",
            license="Apache-2.0",
            provenance="upstream: sarvamai/sarvam-105b",
            is_main_model=True
        )
    )
    runtime: ModelRuntimeConfig = Field(default_factory=ModelRuntimeConfig)
    loading: ModelLoadingConfig = Field(default_factory=ModelLoadingConfig)

settings = Settings()
