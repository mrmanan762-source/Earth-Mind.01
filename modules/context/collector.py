import concurrent.futures
from typing import Dict, List, Optional
from core.errors.exceptions import ContextProviderError
from core.logging.logger import get_logger
from modules.context.interfaces import ContextProvider
from modules.context.schemas import ContextItem, ContextRequest

logger = get_logger("modules.context.collector")


class ContextCollector:
    """Collects context items from registered ContextProvider interfaces concurrently."""

    def __init__(self, providers: Optional[List[ContextProvider]] = None):
        self._providers: Dict[str, ContextProvider] = {}
        if providers:
            for p in providers:
                self.register_provider(p)

    def register_provider(self, provider: ContextProvider) -> None:
        self._providers[provider.provider_name] = provider
        logger.info(f"Registered context provider: {provider.provider_name}")

    def collect(self, request: ContextRequest) -> tuple[List[ContextItem], List[str], List[str]]:
        """
        Concurrently collects context items from registered providers.
        Returns tuple of (collected_items, warnings, errors).
        """
        items: List[ContextItem] = []
        warnings: List[str] = []
        errors: List[str] = []

        if not self._providers:
            logger.warning("No context providers registered in collector.")
            return items, warnings, errors

        timeout = request.policy.timeout_seconds if request.policy else 5.0

        with concurrent.futures.ThreadPoolExecutor(max_workers=len(self._providers)) as executor:
            future_to_provider = {
                executor.submit(p.get_context, request): name
                for name, p in self._providers.items()
            }

            for future in concurrent.futures.as_completed(future_to_provider):
                provider_name = future_to_provider[future]
                try:
                    provider_items = future.result(timeout=timeout)
                    if provider_items:
                        items.extend(provider_items)
                        logger.debug(f"Collected {len(provider_items)} items from '{provider_name}'")
                except concurrent.futures.TimeoutError:
                    msg = f"Provider '{provider_name}' timed out after {timeout} seconds."
                    logger.error(msg)
                    errors.append(msg)
                    if request.policy and provider_name in request.policy.required_providers:
                        logger.error(f"Required provider '{provider_name}' timed out.")
                except Exception as e:
                    msg = f"Provider '{provider_name}' failed: {str(e)}"
                    logger.error(msg)
                    errors.append(msg)
                    if request.policy and provider_name in request.policy.required_providers:
                        logger.error(f"Required provider '{provider_name}' failed.")

        return items, warnings, errors
