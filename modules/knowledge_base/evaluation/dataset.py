"""Stage R15 Evaluation Dataset Repository & Benchmark Query Sets."""

import json
import os
from typing import Dict, List, Optional
from core.errors.exceptions import InvalidEvaluationDatasetError
from core.logging.logger import get_logger
from core.schemas.evaluation import EvaluationCase, EvaluationDataset

logger = get_logger("modules.knowledge_base.evaluation.dataset")


DEFAULT_BENCHMARK_CASES = [
    EvaluationCase(
        case_id="case_agri_gap_001",
        query_text="What are the core Good Agricultural Practices (GAP) for land selection and site history?",
        language="en",
        domain_category="crop_management",
        expected_relevant_doc_ids=["doc_src_icar_gap_001"],
        expected_relevant_chunk_ids=["chk_ku_ver_src_icar_gap_001_1_0_001_001", "chk_ku_ver_src_icar_gap_001_1_0_002_001"],
        expected_source_types=["KNOWLEDGE_BASE"],
        difficulty="easy",
        metadata={"topic": "Good Agricultural Practices", "crop": "general"},
    ),
    EvaluationCase(
        case_id="case_agri_gap_002_hi",
        query_text="भूमि चयन और मृदा स्वास्थ्य के लिए अच्छे कृषि अभ्यास क्या हैं?",
        language="hi",
        domain_category="crop_management",
        expected_relevant_doc_ids=["doc_src_icar_gap_001", "doc_src_dafw_shc_001"],
        expected_relevant_chunk_ids=["chk_ku_ver_src_icar_gap_001_1_0_002_001"],
        expected_source_types=["KNOWLEDGE_BASE"],
        difficulty="medium",
        metadata={"topic": "GAP and Soil Health", "crop": "general"},
    ),
    EvaluationCase(
        case_id="case_rice_disease_001",
        query_text="How to identify and manage Bacterial Leaf Blight and Yellow Stem Borer in paddy rice?",
        language="en",
        domain_category="crop_disease",
        expected_relevant_doc_ids=["doc_src_icar_rice_001"],
        expected_source_types=["KNOWLEDGE_BASE"],
        difficulty="medium",
        metadata={"topic": "Rice Diseases & Pests", "crop": "rice"},
    ),
    EvaluationCase(
        case_id="case_rice_disease_002_hi",
        query_text="धान की फसल में झुलसा रोग और तना छेदक कीट की रोकथाम कैसे करें?",
        language="hi",
        domain_category="crop_disease",
        expected_relevant_doc_ids=["doc_src_icar_rice_001"],
        expected_source_types=["KNOWLEDGE_BASE"],
        difficulty="medium",
        metadata={"topic": "Paddy Pest Control", "crop": "rice"},
    ),
    EvaluationCase(
        case_id="case_wheat_rust_001",
        query_text="What are the symptoms and IPM strategies for Yellow Rust and Karnal Bunt in wheat?",
        language="en",
        domain_category="pests",
        expected_relevant_doc_ids=["doc_src_ncipm_wheat_001"],
        expected_source_types=["KNOWLEDGE_BASE"],
        difficulty="easy",
        metadata={"topic": "Wheat Rust & Bunt", "crop": "wheat"},
    ),
    EvaluationCase(
        case_id="case_soil_shc_001",
        query_text="What parameters are measured under the Soil Health Card scheme and recommended fertilizer application?",
        language="en",
        domain_category="soil",
        expected_relevant_doc_ids=["doc_src_dafw_shc_001", "doc_src_iiss_fert_001"],
        expected_source_types=["KNOWLEDGE_BASE"],
        difficulty="medium",
        metadata={"topic": "Soil Health Card", "crop": "general"},
    ),
    EvaluationCase(
        case_id="case_irrigation_pmksy_001",
        query_text="How does drip and sprinkler micro-irrigation increase water use efficiency under PMKSY?",
        language="en",
        domain_category="irrigation",
        expected_relevant_doc_ids=["doc_src_nmsa_pmksy_001"],
        expected_source_types=["KNOWLEDGE_BASE"],
        difficulty="medium",
        metadata={"topic": "Micro Irrigation PMKSY", "crop": "general"},
    ),
    EvaluationCase(
        case_id="case_climate_dryland_001",
        query_text="What contingency management plans exist for drought and delayed monsoon in rainfed farming?",
        language="en",
        domain_category="weather_related",
        expected_relevant_doc_ids=["doc_src_crida_tnau_001"],
        expected_source_types=["KNOWLEDGE_BASE"],
        difficulty="hard",
        metadata={"topic": "Dryland Contingency", "crop": "rainfed"},
    ),
    EvaluationCase(
        case_id="case_kvk_advisory_001",
        query_text="What role do Krishi Vigyan Kendras (KVK) play in front-line demonstrations and farmer training?",
        language="en",
        domain_category="government_guidance",
        expected_relevant_doc_ids=["doc_src_icar_kvk_001"],
        expected_source_types=["KNOWLEDGE_BASE"],
        difficulty="easy",
        metadata={"topic": "KVK Extension", "crop": "general"},
    ),
    EvaluationCase(
        case_id="case_negative_query_001",
        query_text="Quantum physics application in interstellar rocket propulsion mechanics",
        language="en",
        domain_category="out_of_domain",
        expected_relevant_doc_ids=[],
        expected_relevant_chunk_ids=[],
        expected_source_types=[],
        difficulty="edge_case",
        metadata={"topic": "Irrelevant / Negative Query"},
    ),
]


class EvaluationDatasetRepository:
    """In-memory and file-backed evaluation dataset repository."""

    def __init__(self, storage_dir: Optional[str] = None):
        self.storage_dir = storage_dir
        self._datasets: Dict[str, EvaluationDataset] = {}

        # Load default benchmark dataset
        default_ds = EvaluationDataset(
            dataset_id="ds_earthmind_agri_v1",
            name="EarthMind Agricultural RAG Benchmark Dataset",
            version="1.0.0",
            description="Benchmark dataset covering GAP, Rice/Wheat diseases, Soil Health, PMKSY, KVK, and negative controls.",
            cases=DEFAULT_BENCHMARK_CASES,
            created_at="2026-03-01T00:00:00Z",
            metadata={"domain": "agriculture", "multilingual": True},
        )
        self.save_dataset(default_ds)

    def get_dataset(self, dataset_id: str) -> Optional[EvaluationDataset]:
        """Retrieves a dataset by ID."""
        return self._datasets.get(dataset_id)

    def list_datasets(self) -> List[EvaluationDataset]:
        """Returns all registered datasets."""
        return list(self._datasets.values())

    def save_dataset(self, dataset: EvaluationDataset) -> None:
        """Saves or updates a dataset."""
        if not dataset.dataset_id:
            raise InvalidEvaluationDatasetError("Dataset ID cannot be empty.")
        self._datasets[dataset.dataset_id] = dataset

        if self.storage_dir:
            os.makedirs(self.storage_dir, exist_ok=True)
            filepath = os.path.join(self.storage_dir, f"{dataset.dataset_id}.json")
            try:
                with open(filepath, "w", encoding="utf-8") as f:
                    f.write(dataset.model_dump_json(indent=2))
            except Exception as e:
                logger.warning(f"Failed to persist dataset to {filepath}: {e}")

    def load_from_file(self, filepath: str) -> EvaluationDataset:
        """Loads an EvaluationDataset from a JSON file."""
        if not os.path.exists(filepath):
            raise InvalidEvaluationDatasetError(f"Dataset file not found: {filepath}")
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
            ds = EvaluationDataset.model_validate(data)
            self.save_dataset(ds)
            return ds
        except Exception as e:
            raise InvalidEvaluationDatasetError(f"Failed to parse evaluation dataset JSON from {filepath}: {str(e)}")
