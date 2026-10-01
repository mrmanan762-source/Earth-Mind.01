"""Evaluation Dataset Loader and Manager for EarthMind Stage R15."""

import json
from pathlib import Path
from typing import List, Optional, Union

from core.interfaces.evaluation import IEvaluationDatasetLoader
from core.schemas.evaluation import EvaluationCase, EvaluationDataset


class EvaluationDatasetLoader(IEvaluationDatasetLoader):
    """Loads evaluation datasets from local JSON files or default benchmark path."""

    DEFAULT_DATASET_PATH = Path(__file__).resolve().parents[3] / "data" / "evaluation" / "agri_rag_eval_v1.json"

    def load_dataset(self, dataset_path_or_id: Optional[str] = None) -> EvaluationDataset:
        """
        Loads an EvaluationDataset from specified path, ID, or default benchmark file.
        """
        path = None
        if dataset_path_or_id:
            candidate_path = Path(dataset_path_or_id)
            if candidate_path.exists() and candidate_path.is_file():
                path = candidate_path
            else:
                # Check relative to data/evaluation
                alt_path = Path(__file__).resolve().parents[3] / "data" / "evaluation" / f"{dataset_path_or_id}.json"
                if alt_path.exists() and alt_path.is_file():
                    path = alt_path

        if not path:
            path = self.DEFAULT_DATASET_PATH

        if not path.exists():
            raise FileNotFoundError(f"Evaluation dataset file not found at: {path}")

        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        return EvaluationDataset.model_validate(data)


class EvaluationDatasetManager:
    """Provides filtering, subset creation, and validation operations over EvaluationDatasets."""

    @staticmethod
    def filter_by_language(dataset: EvaluationDataset, language: str) -> EvaluationDataset:
        """Filter dataset cases by language code."""
        filtered_cases = [c for c in dataset.cases if c.language.lower() == language.lower()]
        return dataset.model_copy(
            update={
                "dataset_id": f"{dataset.dataset_id}_lang_{language}",
                "cases": filtered_cases,
            }
        )

    @staticmethod
    def filter_by_domain(dataset: EvaluationDataset, domain: str) -> EvaluationDataset:
        """Filter dataset cases by domain category."""
        filtered_cases = [c for c in dataset.cases if c.domain_category.lower() == domain.lower()]
        return dataset.model_copy(
            update={
                "dataset_id": f"{dataset.dataset_id}_domain_{domain}",
                "cases": filtered_cases,
            }
        )
