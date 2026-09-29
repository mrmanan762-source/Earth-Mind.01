"""Retrieval Query Builder for Stage R9 Query Processing."""

from typing import Any, Dict, List, Optional
from core.schemas.query import (
    AgriculturalMetadata,
    DenseQuery,
    QueryExpansion,
    QueryMetadata,
    QueryProcessingRequest,
    RetrievalQuery,
    SparseQuery,
    StructuredQueryFilter,
)


class RetrievalQueryBuilder:
    """
    Assembles normalized text, expansions, extracted metadata, and structured filters
    into a complete RetrievalQuery payload directly consumable by R5/R6/R7 retrieval interfaces.
    """

    def build_retrieval_query(
        self,
        request: QueryProcessingRequest,
        normalized_query: str,
        query_metadata: QueryMetadata,
        expansions: List[QueryExpansion],
        dense_vector: Optional[List[float]] = None,
        sparse_indices: Optional[List[int]] = None,
        sparse_values: Optional[List[float]] = None,
    ) -> RetrievalQuery:
        # 1. Build DenseQuery
        dense_q = DenseQuery(
            dense_query_text=normalized_query,
            dense_vector=dense_vector,
            top_k=request.dense_top_k,
            embedding_model_hint=None,
        )

        # 2. Extract lexical terms for SparseQuery
        lexical_tokens = [t for t in normalized_query.split() if len(t) > 1]
        expanded_term_strings = [exp.expanded_text for exp in expansions]

        # Basic term weighting
        weights: Dict[str, float] = {}
        for token in lexical_tokens:
            weights[token] = 1.0
        for exp in expansions:
            weights[exp.expanded_text] = exp.weight

        sparse_q = SparseQuery(
            sparse_query_text=normalized_query,
            lexical_terms=lexical_tokens,
            expanded_terms=expanded_term_strings,
            term_weights=weights,
            sparse_indices=sparse_indices,
            sparse_values=sparse_values,
        )

        # 3. Construct structured filters from extracted agricultural metadata & explicit request filters
        filters: List[StructuredQueryFilter] = []

        # Explicit request filters take primary precedence
        if request.filters:
            for field, val in request.filters.items():
                filters.append(StructuredQueryFilter(field=field, operator="eq", value=val))

        # Extracted agricultural metadata filters (if not already present in explicit filters)
        ag_meta = query_metadata.agricultural_metadata
        existing_fields = {f.field for f in filters}

        if ag_meta.crop and "crop" not in existing_fields:
            filters.append(StructuredQueryFilter(field="crop", operator="eq", value=ag_meta.crop))
        if ag_meta.disease_pest and "disease_pest" not in existing_fields:
            filters.append(StructuredQueryFilter(field="disease_pest", operator="eq", value=ag_meta.disease_pest))
        if ag_meta.soil_type and "soil_type" not in existing_fields:
            filters.append(StructuredQueryFilter(field="soil_type", operator="eq", value=ag_meta.soil_type))
        if ag_meta.region and "region" not in existing_fields:
            filters.append(StructuredQueryFilter(field="region", operator="eq", value=ag_meta.region))
        if ag_meta.season and "season" not in existing_fields:
            filters.append(StructuredQueryFilter(field="season", operator="eq", value=ag_meta.season))

        # 4. Provenance tracking
        provenance: Dict[str, Any] = {
            "r9_version": "1.0.0",
            "original_query": request.query_text,
            "normalized_query": normalized_query,
            "expansions_count": len(expansions),
            "filters_count": len(filters),
            "language": query_metadata.language,
        }

        return RetrievalQuery(
            original_query=request.query_text,
            normalized_query=normalized_query,
            expanded_queries=expansions,
            dense_query=dense_q,
            sparse_query=sparse_q,
            structured_filters=filters,
            metadata=query_metadata,
            top_k=request.top_k,
            dense_top_k=request.dense_top_k,
            sparse_top_k=request.sparse_top_k,
            collection_name=request.collection_name,
            provenance=provenance,
            request_id=request.request_id,
        )
