import os
import tempfile
import pytest
from core.config.settings import settings, KnowledgeBaseStorageSettings
from modules.database.sqlite_db import SQLiteDatabaseService
from modules.knowledge_base.storage.local_artifact_storage import LocalArtifactStorage
from modules.knowledge_base.storage.canonical_repository import CanonicalKnowledgeRepository
from modules.knowledge_base.storage.index_placeholder import KnowledgeIndexPlaceholder
from modules.knowledge_base.storage.exceptions import (
    ArtifactNotFoundError,
    RecordNotFoundError,
    StorageConfigurationError,
)

def test_kb_storage_settings_resolution():
    kb_settings = settings.kb_storage
    assert isinstance(kb_settings, KnowledgeBaseStorageSettings)
    assert kb_settings.kb_raw_artifact_dir is not None
    assert kb_settings.kb_storage_backend == "local_filesystem"
    assert kb_settings.kb_index_backend == "placeholder"
    assert kb_settings.kb_db_path is not None

def test_local_artifact_storage_crud():
    with tempfile.TemporaryDirectory() as temp_dir:
        storage = LocalArtifactStorage(base_dir=temp_dir)

        # Test save text artifact
        art_id = "art_001"
        content = "Soil Management Guidelines for Wheat"
        meta = {"domain": "soil", "crop": "wheat"}

        saved_id = storage.save_artifact(art_id, content, meta)
        assert saved_id == art_id
        assert storage.has_artifact(art_id)

        # Test read
        data_bytes = storage.get_artifact(art_id)
        assert data_bytes.decode("utf-8") == content

        # Test metadata
        read_meta = storage.get_artifact_metadata(art_id)
        assert read_meta is not None
        assert read_meta["domain"] == "soil"
        assert read_meta["crop"] == "wheat"
        assert read_meta["size_bytes"] == len(content.encode("utf-8"))

        # Test list
        art_list = storage.list_artifacts()
        assert art_id in art_list

        # Test delete
        deleted = storage.delete_artifact(art_id)
        assert deleted is True
        assert not storage.has_artifact(art_id)

        # Test missing artifact error
        with pytest.raises(ArtifactNotFoundError):
            storage.get_artifact("non_existent_id")

        with pytest.raises(ArtifactNotFoundError):
            storage.delete_artifact("non_existent_id")

def test_canonical_knowledge_repository():
    db = SQLiteDatabaseService(":memory:")
    db.connect()

    repo = CanonicalKnowledgeRepository(db_service=db)
    repo.initialize_schema()

    # Save record
    rec_type = "Document"
    rec_id = "doc_101"
    doc_data = {
        "title": "Integrated Pest Management Guide",
        "domain": "plant_protection",
        "author": "Agricultural Extension"
    }

    repo.save_record(rec_type, rec_id, doc_data)

    # Get record
    retrieved = repo.get_record(rec_type, rec_id)
    assert retrieved is not None
    assert retrieved["title"] == "Integrated Pest Management Guide"
    assert retrieved["_meta"]["record_type"] == rec_type
    assert retrieved["_meta"]["record_id"] == rec_id

    # List records with filters
    repo.save_record(rec_type, "doc_102", {"title": "Rice Fertilization", "domain": "soil"})

    all_docs = repo.list_records(rec_type)
    assert len(all_docs) == 2

    soil_docs = repo.list_records(rec_type, filters={"domain": "soil"})
    assert len(soil_docs) == 1
    assert soil_docs[0]["title"] == "Rice Fertilization"

    # Delete record
    deleted = repo.delete_record(rec_type, rec_id)
    assert deleted is True
    assert repo.get_record(rec_type, rec_id) is None

    with pytest.raises(RecordNotFoundError):
        repo.delete_record(rec_type, "non_existent_rec")

    db.disconnect()

def test_knowledge_index_placeholder():
    idx = KnowledgeIndexPlaceholder(backend_name="placeholder")

    status = idx.index_status()
    assert status["status"] == "PLACEHOLDER_READY"
    assert status["backend"] == "placeholder"
    assert status["derived_from_canonical"] is True
    assert status["authoritative"] is False

    rec_id = idx.register_index_record({"chunk_id": "chk_001", "vector_dim": 768})
    assert rec_id == "chk_001"
    assert idx.index_status()["record_count"] == 1

    searchResults = idx.search_placeholder(query="wheat diseases")
    assert len(searchResults) == 1
    assert searchResults[0]["status"] == "SEARCH_DEFERRED"
