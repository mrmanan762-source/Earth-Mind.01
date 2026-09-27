"""Production-Grade BM25 Lexical Sparse Provider and Multilingual Processor for EarthMind.

Implements ISparseRepresentationProvider interface and provides domain-aware tokenization
for English, Hindi, Devanagari, mixed-language Indian text, and agricultural terminology.

Key Features:
- Non-destructive normalization preserving agricultural terms, crop names, diseases, dosages, pH, temp.
- Multilingual tokenization supporting English and Devanagari / Indic scripts.
- BM25 term weighting returning index-ordered, aligned SparseVector payloads.
- Configurable k1, b, average document length, and vocabulary size parameters.
- Idempotent and deterministic term index hashing mapping to fixed vocabulary space.
"""

import hashlib
import math
import re
import time
from typing import Any, Dict, List, Optional, Set, Tuple

from core.errors.exceptions import (
    InvalidSparseInputError,
    SparseConfigurationError,
    SparseProviderUnavailableError,
)
from core.interfaces.sparse import ISparseRepresentationProvider
from core.schemas.embedding import (
    EmbeddingMetadata,
    EmbeddingStatus,
    ModelMetadata,
    ProviderMetadata,
    SparseVector,
)
from core.schemas.sparse import (
    SparseRepresentationRequest,
    SparseRepresentationResponse,
)

# Core English stopwords (excluding agricultural domain keywords like 'crop', 'plant', 'field', 'water', 'yield')
STANDARD_ENGLISH_STOPWORDS: Set[str] = {
    "a", "about", "above", "after", "again", "against", "all", "am", "an", "and", "any", "are",
    "as", "at", "be", "because", "been", "before", "being", "below", "between", "both", "but",
    "by", "could", "did", "do", "does", "doing", "down", "during", "each", "few", "for", "from",
    "further", "had", "has", "have", "having", "he", "her", "here", "hers", "herself", "him",
    "himself", "his", "how", "i", "if", "in", "into", "is", "it", "its", "itself", "just",
    "me", "more", "most", "my", "myself", "no", "nor", "not", "now", "of", "off", "on", "once",
    "only", "or", "other", "our", "ours", "ourselves", "out", "over", "own", "same", "she",
    "should", "so", "some", "such", "than", "that", "the", "their", "theirs", "them", "themselves",
    "then", "there", "these", "they", "this", "those", "through", "to", "too", "under", "until",
    "up", "very", "was", "we", "were", "what", "when", "where", "which", "while", "who", "whom",
    "why", "with", "would", "you", "your", "yours", "yourself", "yourselves",
}

# Core Hindi / Devanagari stopwords (excluding key agricultural concepts)
STANDARD_HINDI_STOPWORDS: Set[str] = {
    "का", "के", "की", "को", "में", "से", "पर", "और", "या", "है", "हैं", "था", "थी", "थे",
    "हो", "होता", "होती", "होते", "हुए", "हुआ", "हुई", "यह", "वह", "इस", "उस", "इन्हें", "उन्हें",
    "कि", "जो", "तो", "ने", "ही", "भी", "द्वारा", "लिये", "लिए", "अपने", "अपनी", "अपना",
}

# Regex to detect Devanagari script characters
DEVANAGARI_REGEX = re.compile(r"[\u0900-\u097F]")

# Regex to preserve agricultural parameters like 10kg/ha, pH 6.5, 25°C, NPK 10:26:26
AGRI_PARAM_REGEX = re.compile(
    r"\b(?:\d+(?:\.\d+)?(?:\s*kg/ha|\s*t/ha|\s*g/l|\s*mg/l|\s*°c|\s*c|\s*cm|\s*mm|\s*ph|\s*%|\s*npk)?)\b|"
    r"\bph\s*\d+(?:\.\d+)?\b|\bnpk\s*\d+:\d+:\d+\b",
    re.IGNORECASE,
)


class MultilingualSparseProcessor:
    """Processor responsible for non-destructive multilingual tokenization and term processing."""

    def __init__(
        self,
        vocabulary_size: int = 30000,
        enable_stopwords_filter: bool = True,
        extra_stopwords: Optional[Set[str]] = None,
    ):
        self.vocabulary_size = vocabulary_size
        self.enable_stopwords_filter = enable_stopwords_filter
        self.stopwords = set(STANDARD_ENGLISH_STOPWORDS).union(STANDARD_HINDI_STOPWORDS)
        if extra_stopwords:
            self.stopwords.update(extra_stopwords)

    def is_devanagari(self, text: str) -> bool:
        """Return True if text contains Devanagari characters."""
        return bool(DEVANAGARI_REGEX.search(text))

    def normalize_text(self, text: str) -> str:
        """Non-destructively normalizes text while preserving agricultural terms and parameters."""
        if not text:
            return ""

        # Lowercase for script-neutral handling (Devanagari remains unaffected by lower())
        normalized = text.lower()

        # Replace structural tabs/newlines with spaces
        normalized = re.sub(r"[\t\r\n]+", " ", normalized)

        # Retain Devanagari characters (\u0900-\u097F), alphanumeric ASCII, agricultural parameter symbols (°/.:%), and whitespace
        normalized = re.sub(r"[^\w\s\u0900-\u097F\.\:\%\/°\-]", " ", normalized)

        # Collapse multiple spaces
        normalized = re.sub(r"\s+", " ", normalized).strip()
        return normalized

    def tokenize(self, text: str) -> List[str]:
        """Tokenize normalized text into meaningful term tokens."""
        norm = self.normalize_text(text)
        if not norm:
            return []

        raw_tokens = norm.split(" ")
        tokens: List[str] = []

        for tok in raw_tokens:
            tok_clean = tok.strip(".,:-/ ")
            if not tok_clean:
                continue

            # Length filter: allow single Devanagari characters or digits/letters >= 2
            if len(tok_clean) < 2 and not self.is_devanagari(tok_clean) and not tok_clean.isdigit():
                continue

            # Filter stopwords if enabled
            if self.enable_stopwords_filter and tok_clean in self.stopwords:
                continue

            tokens.append(tok_clean)

        return tokens

    def map_term_to_index(self, term: str) -> int:
        """Map string term deterministically to integer index in vocabulary space [0, vocabulary_size - 1]."""
        md5_hash = hashlib.md5(term.encode("utf-8")).hexdigest()
        return int(md5_hash[:8], 16) % self.vocabulary_size


class BM25SparseProvider(ISparseRepresentationProvider):
    """Production-grade BM25 Lexical Sparse Provider implementing ISparseRepresentationProvider."""

    def __init__(
        self,
        provider_name: str = "bm25_sparse",
        model_name: str = "earthmind-bm25-agri-v1",
        model_version: str = "1.0.0",
        vocabulary_id: str = "agri-vocab-30k",
        vocabulary_size: int = 30000,
        k1: float = 1.2,
        b: float = 0.75,
        avg_doc_len: float = 256.0,
        license: str = "Apache-2.0",
        provenance: str = "EarthMind Multilingual Agricultural BM25 Engine",
        available: bool = True,
        idf_table: Optional[Dict[str, float]] = None,
        processor: Optional[MultilingualSparseProcessor] = None,
    ):
        self.provider_name = provider_name
        self.model_name = model_name
        self.model_version = model_version
        self.vocabulary_id = vocabulary_id
        self.vocabulary_size = vocabulary_size
        self.k1 = k1
        self.b = b
        self.avg_doc_len = avg_doc_len
        self.license = license
        self.provenance = provenance
        self._available = available
        self.idf_table = idf_table or {}
        self.processor = processor or MultilingualSparseProcessor(vocabulary_size=vocabulary_size)

    def is_available(self) -> bool:
        return self._available

    def set_availability(self, available: bool) -> None:
        self._available = available

    def validate_config(self) -> bool:
        if self.vocabulary_size <= 0:
            raise SparseConfigurationError(f"Invalid vocabulary size {self.vocabulary_size}. Must be > 0.")
        if self.k1 < 0:
            raise SparseConfigurationError(f"Invalid k1 value {self.k1}. Must be >= 0.")
        if not (0.0 <= self.b <= 1.0):
            raise SparseConfigurationError(f"Invalid b value {self.b}. Must be between 0.0 and 1.0.")
        if self.avg_doc_len <= 0:
            raise SparseConfigurationError(f"Invalid avg_doc_len {self.avg_doc_len}. Must be > 0.")
        return True

    def get_provider_metadata(self) -> ProviderMetadata:
        return ProviderMetadata(
            provider_name=self.provider_name,
            provider_type="lexical_bm25",
            is_mock=False,
            extra={
                "k1": self.k1,
                "b": self.b,
                "avg_doc_len": self.avg_doc_len,
            },
        )

    def get_model_metadata(self) -> ModelMetadata:
        return ModelMetadata(
            model_name=self.model_name,
            model_version=self.model_version,
            dimension=self.vocabulary_size,
            license=self.license,
            provenance=self.provenance,
            commercial_use_allowed=True,
            extra={
                "vocabulary_id": self.vocabulary_id,
                "vocabulary_size": self.vocabulary_size,
                "sparse_type": "lexical_bm25",
            },
        )

    def get_vocabulary_id(self) -> Optional[str]:
        return self.vocabulary_id

    def get_vocabulary_size(self) -> Optional[int]:
        return self.vocabulary_size

    def compute_idf(self, term: str, total_docs: int = 1000, doc_freq: int = 10) -> float:
        """Computes BM25 Inverse Document Frequency (IDF) for a term."""
        if term in self.idf_table:
            return self.idf_table[term]
        # Standard BM25 Robertson-Spärck Jones IDF with smoothing
        df = max(1, doc_freq)
        idf = math.log(1.0 + (total_docs - df + 0.5) / (df + 0.5))
        return max(0.1, idf)

    def generate_sparse_vector(self, text: str) -> SparseVector:
        """Generates aligned, index-ordered SparseVector for a text string using BM25 weighting."""
        tokens = self.processor.tokenize(text)
        if not tokens:
            return SparseVector(indices=[], values=[], terms={}, dimension=self.vocabulary_size)

        doc_len = len(tokens)

        # Count term frequencies
        tf_dict: Dict[str, int] = {}
        for tok in tokens:
            tf_dict[tok] = tf_dict.get(tok, 0) + 1

        # Map terms to vocabulary index and compute BM25 weights
        index_weight_map: Dict[int, Tuple[float, str]] = {}

        for term, tf in tf_dict.items():
            index_val = self.processor.map_term_to_index(term)
            idf = self.compute_idf(term)

            # BM25 term weighting formula
            num = tf * (self.k1 + 1.0)
            denom = tf + self.k1 * (1.0 - self.b + self.b * (doc_len / self.avg_doc_len))
            bm25_weight = round(idf * (num / denom), 4)

            if bm25_weight > 0.0:
                if index_val in index_weight_map:
                    # Accumulate in case of hash collision
                    prev_w, _ = index_weight_map[index_val]
                    index_weight_map[index_val] = (round(prev_w + bm25_weight, 4), term)
                else:
                    index_weight_map[index_val] = (bm25_weight, term)

        # Sort indices strictly in ascending order
        sorted_indices = sorted(index_weight_map.keys())
        indices = sorted_indices
        values = [index_weight_map[idx][0] for idx in sorted_indices]
        terms = {index_weight_map[idx][1]: index_weight_map[idx][0] for idx in sorted_indices}

        return SparseVector(
            indices=indices,
            values=values,
            terms=terms,
            dimension=self.vocabulary_size,
        )

    def generate_sparse(
        self, request: SparseRepresentationRequest
    ) -> SparseRepresentationResponse:
        start_time = time.time()

        if not self.is_available():
            raise SparseProviderUnavailableError(self.provider_name, "BM25SparseProvider is currently set to unavailable.")

        self.validate_config()

        try:
            request.validate_request()
        except ValueError as e:
            raise InvalidSparseInputError(str(e))

        sparse_vectors: List[SparseVector] = []
        for text in request.texts:
            sparse_vectors.append(self.generate_sparse_vector(text))

        elapsed_ms = round((time.time() - start_time) * 1000, 2)

        return SparseRepresentationResponse(
            sparse_vectors=sparse_vectors,
            status=EmbeddingStatus.SUCCESS,
            provider_metadata=self.get_provider_metadata(),
            model_metadata=self.get_model_metadata(),
            vocabulary_id=self.vocabulary_id,
            vocabulary_size=self.vocabulary_size,
            metadata=EmbeddingMetadata(
                provider=self.provider_name,
                model=self.model_name,
                model_version=self.model_version,
                dimension=self.vocabulary_size,
                processing_time_ms=elapsed_ms,
                source_id=request.source_id,
            ),
        )
