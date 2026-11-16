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
    # --- Phase 2 expansion: remaining target crops ---
    EvaluationCase(
        case_id="case_maize_faw_001",
        query_text="How is fall armyworm managed in maize and what are the critical growth stages for irrigation?",
        language="en",
        domain_category="pests",
        expected_relevant_doc_ids=["doc_src_icar_iimr_maize_001"],
        expected_source_types=["KNOWLEDGE_BASE"],
        difficulty="medium",
        metadata={"topic": "Maize Fall Armyworm & Irrigation", "crop": "maize"},
    ),
    EvaluationCase(
        case_id="case_potato_lateblight_001",
        query_text="What are the symptoms of late blight in potato and how is it managed?",
        language="en",
        domain_category="crop_disease",
        expected_relevant_doc_ids=["doc_src_icar_cpri_potato_001"],
        expected_source_types=["KNOWLEDGE_BASE"],
        difficulty="easy",
        metadata={"topic": "Potato Late Blight", "crop": "potato"},
    ),
    EvaluationCase(
        case_id="case_onion_thrips_001",
        query_text="How do thrips damage onion and what integrated practices reduce the infestation?",
        language="en",
        domain_category="pests",
        expected_relevant_doc_ids=["doc_src_icar_dogr_onion_001"],
        expected_source_types=["KNOWLEDGE_BASE"],
        difficulty="medium",
        metadata={"topic": "Onion Thrips", "crop": "onion"},
    ),
    EvaluationCase(
        case_id="case_tomato_leafcurl_001",
        query_text="What causes tomato leaf curl virus and which pest management practices reduce its spread?",
        language="en",
        domain_category="crop_disease",
        expected_relevant_doc_ids=["doc_src_icar_iihr_tomato_001"],
        expected_source_types=["KNOWLEDGE_BASE"],
        difficulty="medium",
        metadata={"topic": "Tomato Leaf Curl", "crop": "tomato"},
    ),
    EvaluationCase(
        case_id="case_pea_powderymildew_001",
        query_text="What are the symptoms and management of powdery mildew in field pea?",
        language="en",
        domain_category="crop_disease",
        expected_relevant_doc_ids=["doc_src_icar_iipr_pea_001"],
        expected_source_types=["KNOWLEDGE_BASE"],
        difficulty="easy",
        metadata={"topic": "Pea Powdery Mildew", "crop": "pea"},
    ),
    EvaluationCase(
        case_id="case_chickpea_podborer_001",
        query_text="How is pod borer managed in chickpea and what are the key disease symptoms?",
        language="en",
        domain_category="pests",
        expected_relevant_doc_ids=["doc_src_icar_iipr_chickpea_001"],
        expected_source_types=["KNOWLEDGE_BASE"],
        difficulty="medium",
        metadata={"topic": "Chickpea Pod Borer", "crop": "chickpea"},
    ),
    EvaluationCase(
        case_id="case_pigeonpea_wilt_001",
        query_text="What is the recommended spacing and disease management for pigeonpea cultivation?",
        language="en",
        domain_category="crop_management",
        expected_relevant_doc_ids=["doc_src_icar_iipr_pigeonpea_001"],
        expected_source_types=["KNOWLEDGE_BASE"],
        difficulty="medium",
        metadata={"topic": "Pigeonpea Cultivation", "crop": "pigeonpea"},
    ),
    EvaluationCase(
        case_id="case_mustard_aphid_001",
        query_text="How is mustard aphid controlled and why is sulphur important in mustard nutrition?",
        language="en",
        domain_category="pests",
        expected_relevant_doc_ids=["doc_src_icar_drmr_mustard_001"],
        expected_source_types=["KNOWLEDGE_BASE"],
        difficulty="medium",
        metadata={"topic": "Mustard Aphid & Sulphur", "crop": "mustard"},
    ),
    EvaluationCase(
        case_id="case_groundnut_tikka_001",
        query_text="What are the symptoms of tikka disease in groundnut and its integrated management?",
        language="en",
        domain_category="crop_disease",
        expected_relevant_doc_ids=["doc_src_icar_dgr_groundnut_001"],
        expected_source_types=["KNOWLEDGE_BASE"],
        difficulty="medium",
        metadata={"topic": "Groundnut Tikka", "crop": "groundnut"},
    ),
    EvaluationCase(
        case_id="case_soybean_ymv_001",
        query_text="How does yellow mosaic virus affect soybean and how is the whitefly vector managed?",
        language="en",
        domain_category="crop_disease",
        expected_relevant_doc_ids=["doc_src_icar_iisr_soybean_001"],
        expected_source_types=["KNOWLEDGE_BASE"],
        difficulty="medium",
        metadata={"topic": "Soybean Yellow Mosaic", "crop": "soybean"},
    ),
    EvaluationCase(
        case_id="case_sugarcane_redrot_001",
        query_text="What are the symptoms of red rot in sugarcane and the recommended sett treatment?",
        language="en",
        domain_category="crop_disease",
        expected_relevant_doc_ids=["doc_src_icar_iisr_sugarcane_001"],
        expected_source_types=["KNOWLEDGE_BASE"],
        difficulty="medium",
        metadata={"topic": "Sugarcane Red Rot", "crop": "sugarcane"},
    ),
    EvaluationCase(
        case_id="case_lentil_001",
        query_text="What is the package of practices for lentil cultivation including sowing time and disease management?",
        language="en",
        domain_category="crop_management",
        expected_relevant_doc_ids=["doc_src_icar_iipr_lentil_001"],
        expected_source_types=["KNOWLEDGE_BASE"],
        difficulty="easy",
        metadata={"topic": "Lentil Cultivation", "crop": "lentil"},
    ),
    # --- Phase 2 expansion: Domain B Soil Intelligence ---
    EvaluationCase(
        case_id="case_soil_classification_001",
        query_text="How are soils classified by texture and structure and how does pH affect nutrient availability?",
        language="en",
        domain_category="soil",
        expected_relevant_doc_ids=["doc_src_icar_nbss_soil_001"],
        expected_source_types=["KNOWLEDGE_BASE"],
        difficulty="medium",
        metadata={"topic": "Soil Classification & pH", "crop": "general"},
    ),
    EvaluationCase(
        case_id="case_soil_salinity_001",
        query_text="What is the difference between saline and sodic soils and how are they reclaimed?",
        language="en",
        domain_category="soil",
        expected_relevant_doc_ids=["doc_src_icar_nbss_soil_001"],
        expected_source_types=["KNOWLEDGE_BASE"],
        difficulty="hard",
        metadata={"topic": "Soil Salinity & Sodicity", "crop": "general"},
    ),
    EvaluationCase(
        case_id="case_soil_health_card_params_001",
        query_text="Which parameters are reported on a Soil Health Card and how are low, medium and high ratings interpreted?",
        language="en",
        domain_category="soil",
        expected_relevant_doc_ids=["doc_src_dafw_shc_ref_002", "doc_src_dafw_shc_001"],
        expected_source_types=["KNOWLEDGE_BASE"],
        difficulty="medium",
        metadata={"topic": "Soil Health Card Interpretation", "crop": "general"},
    ),
    # --- Phase 2 expansion: Domain C Satellite / Remote Sensing ---
    EvaluationCase(
        case_id="case_rs_ndvi_001",
        query_text="How is NDVI calculated and how is it used to monitor crop vegetation health?",
        language="en",
        domain_category="remote_sensing",
        expected_relevant_doc_ids=["doc_src_icar_nbss_rs_001"],
        expected_source_types=["KNOWLEDGE_BASE"],
        difficulty="easy",
        metadata={"topic": "NDVI & Crop Monitoring", "crop": "general"},
    ),
    EvaluationCase(
        case_id="case_rs_resolution_001",
        query_text="What is the difference between spatial, temporal and spectral resolution in satellite imagery?",
        language="en",
        domain_category="remote_sensing",
        expected_relevant_doc_ids=["doc_src_icar_nbss_rs_001"],
        expected_source_types=["KNOWLEDGE_BASE"],
        difficulty="medium",
        metadata={"topic": "Remote Sensing Resolution", "crop": "general"},
    ),
    EvaluationCase(
        case_id="case_rs_limitations_001",
        query_text="What are the limitations of using vegetation indices for crop stress detection?",
        language="en",
        domain_category="remote_sensing",
        expected_relevant_doc_ids=["doc_src_icar_nbss_rs_001"],
        expected_source_types=["KNOWLEDGE_BASE"],
        difficulty="hard",
        metadata={"topic": "Remote Sensing Uncertainty", "crop": "general"},
    ),
    # --- Phase 2 expansion: Domain D General Agriculture ---
    EvaluationCase(
        case_id="case_general_units_001",
        query_text="How are agricultural land units and fertilizer nutrient contents expressed?",
        language="en",
        domain_category="general_agriculture",
        expected_relevant_doc_ids=["doc_src_icar_ext_units_001"],
        expected_source_types=["KNOWLEDGE_BASE"],
        difficulty="easy",
        metadata={"topic": "Agricultural Units", "crop": "general"},
    ),
    EvaluationCase(
        case_id="case_general_inm_ipm_001",
        query_text="What is the difference between integrated nutrient management and integrated pest management?",
        language="en",
        domain_category="general_agriculture",
        expected_relevant_doc_ids=["doc_src_icar_ext_units_001", "doc_src_icar_gap_001"],
        expected_source_types=["KNOWLEDGE_BASE"],
        difficulty="medium",
        metadata={"topic": "INM and IPM", "crop": "general"},
    ),
    EvaluationCase(
        case_id="case_multi_source_nutrient_001",
        query_text="What nutrient management practices combine soil health card guidance and general fertilizer principles?",
        language="en",
        domain_category="soil",
        expected_relevant_doc_ids=["doc_src_dafw_shc_ref_002", "doc_src_iiss_fert_001", "doc_src_icar_ext_units_001"],
        expected_source_types=["KNOWLEDGE_BASE"],
        difficulty="hard",
        metadata={"topic": "Multi-source Nutrient Management", "crop": "general"},
    ),
    EvaluationCase(
        case_id="case_insufficient_evidence_001",
        query_text="What is the exact current wholesale market price of onion in Maharashtra today?",
        language="en",
        domain_category="out_of_domain",
        expected_relevant_doc_ids=[],
        expected_relevant_chunk_ids=[],
        expected_source_types=[],
        difficulty="edge_case",
        metadata={"topic": "Dynamic fact requiring live source", "crop": "onion"},
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
            version="2.0.0",
            description=(
                "Benchmark dataset covering GAP, all 15 target crops, soil intelligence, "
                "satellite/remote sensing, general agriculture, multi-source and negative controls."
            ),
            cases=DEFAULT_BENCHMARK_CASES,
            created_at="2026-03-01T00:00:00Z",
            metadata={"domain": "agriculture", "multilingual": True, "phase": "phase2"},
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
