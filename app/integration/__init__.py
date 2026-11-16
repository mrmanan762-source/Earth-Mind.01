"""Phase 4 integration layer: connects the completed EarthMind modules into one
coherent, executable application workflow without duplicating their logic.

Contents:
- ``capabilities``: typed B5 ``ICapability`` adapters that translate B5 workflow
  step inputs into the established module contracts (B2/B3/B4, Inspector, Memory,
  ULPU, Satellite, Tools).
- ``tool_selection``: deterministic, request-dependent tool selection.
- ``workflow``: the integrated application workflow and its module entry point.
"""

from app.integration.workflow import IntegratedApplicationModule, IntegratedWorkflow

__all__ = ["IntegratedWorkflow", "IntegratedApplicationModule"]
