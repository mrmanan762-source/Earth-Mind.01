"""Phase 2 integration tests: KnowledgeBaseModule wiring, readiness, and persistence.

These tests exercise the real retrieval stack (embedding + dense/sparse indexes +
hybrid retrieval) through the application lifecycle. They do not mock the index or
the embedding provider: readiness and persistence are asserted against a durable
on-disk store.
"""

import shutil
from pathlib import Path

import pytest

from app.main import create_app
from core.schemas.application import ApplicationRequest


@pytest.fixture()
def kb_store(tmp_path, monkeypatch):
    """Isolate the Knowledge Base durable store per test."""
    store = tmp_path / "rag_store"
    monkeypatch.setenv("EARTHMIND_KB_PERSIST_DIR", str(store))
    monkeypatch.setenv("EARTHMIND_ENV", "test")
    yield store
    if store.exists():
        shutil.rmtree(store, ignore_errors=True)


def test_knowledge_base_module_registered_in_bootstrap():
    lifecycle, _ = create_app()
    module = lifecycle.get_module("knowledge_base")
    assert module is not None
    assert module.module_name == "knowledge_base"


def test_knowledge_base_initializes_and_serves_real_evidence(kb_store):
    lifecycle, workflow = create_app()
    lifecycle.initialize_all()
    try:
        kb = lifecycle.get_module("knowledge_base")
        health = kb.get_health()
        assert health["initialized"] is True
        assert health["ready"] is True
        assert health["readiness_reason"] == "READY"
        assert health["indexed_records"] > 0
        assert health["embedding_dimension"] == 1024

        response = workflow.dispatch(
            ApplicationRequest(
                request_id="kb_e2e_1",
                source="test",
                actor="farmer",
                operation="rag_query",
                payload={"query": "What are the symptoms of late blight in potato?"},
                metadata={"target_module": "knowledge_base"},
            )
        )
        assert response.status == "SUCCESS"
        assert response.response, "Expected at least one RAG context contract"
    finally:
        lifecycle.shutdown_all()


def test_knowledge_base_does_not_mutate_shared_rag_settings():
    """The module must not mutate the shared ``settings.rag_integration`` singleton.

    Previously it assigned ``rag_provider.config.enable_web_search`` on the singleton,
    which leaked ``False`` into any later component/test that relies on the default.
    """
    from core.config.settings import settings
    from modules.knowledge_base.kb_module import KnowledgeBaseModule

    before = settings.rag_integration.enable_web_search
    module = KnowledgeBaseModule(enable_web_search=not before)
    cfg = module._resolve_rag_config()
    assert cfg.enable_web_search == (not before)
    assert settings.rag_integration.enable_web_search == before


def test_knowledge_base_survives_restart(kb_store):
    lifecycle, _ = create_app()
    lifecycle.initialize_all()
    first_count = lifecycle.get_module("knowledge_base").get_health()["indexed_records"]
    lifecycle.shutdown_all()
    assert first_count > 0

    # A second lifecycle must reopen the same durable store and stay READY
    # without re-ingesting, proving persistence across application restarts.
    lifecycle2, _ = create_app()
    lifecycle2.initialize_all()
    try:
        health2 = lifecycle2.get_module("knowledge_base").get_health()
        assert health2["initialized"] is True
        assert health2["ready"] is True
        assert health2["indexed_records"] == first_count
    finally:
        lifecycle2.shutdown_all()
