"""
Hebbrix Client

Main client class for interacting with the Hebbrix api.
"""

import os
from typing import Any, Dict, List, Optional

import httpx
from hebbrix.exceptions import (
    AuthenticationError,
    HebbrixError,
    NotFoundError,
    RateLimitError,
    ServerError,
    ValidationError,
)
from hebbrix.resources import (
    AuthResource,
    CollectionsResource,
    ConsolidationResource,
    MemoriesResource,
    MemoryToolsResource,
    ProceduralResource,
    ProofLoopResource,
    RLResource,
    SearchResource,
    TemporalResource,
    WorkingMemoryResource,
    WorldModelResource,
)


class MemoryClient:
    """
    Hebbrix api client.

    Args:
        api_key: API key for authentication
        base_url: Base URL of the API (default: https://api.hebbrix.com)
        timeout: Request timeout in seconds (default: 30)
        source: Collection source ("app" or "api") for data isolation. Falls back to HEBBRIX_SOURCE env var.

    Example:
        >>> client = MemoryClient(api_key="mem_sk_...")
        >>> memory = await client.memories.create(
        ...     collection_id="col_123",
        ...     content="Important note"
        ... )
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: str = "https://api.hebbrix.com",
        timeout: float = 120.0,
        source: Optional[str] = None,
    ):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.source = source or os.getenv("HEBBRIX_SOURCE")

        # HTTP client
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=timeout,
            headers=self._get_headers(),
        )

        # Initialize resources
        self.auth = AuthResource(self)
        self.collections = CollectionsResource(self)
        self.memories = MemoriesResource(self)
        self.search_resource = SearchResource(self)
        self.proofloop = ProofLoopResource(self)
        self.rl = RLResource(self)
        self.procedural = ProceduralResource(self)
        self.temporal = TemporalResource(self)
        self.working_memory = WorkingMemoryResource(self)
        self.consolidation = ConsolidationResource(self)
        self.memory_tools = MemoryToolsResource(self)
        self.world_model = WorldModelResource(self)

    def _get_headers(self) -> Dict[str, str]:
        """Get request headers."""
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "hebbrix-python/2.2.0",
        }

        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        if self.source:
            headers["X-Hebbrix-Source"] = self.source

        return headers

    def _handle_error(self, response: httpx.Response) -> None:
        """Handle error responses."""
        status_code = response.status_code

        try:
            error_data = response.json()
            message = error_data.get("error", {}).get("message", response.text)
        except Exception:
            message = response.text

        if status_code == 401:
            raise AuthenticationError(message)
        elif status_code == 404:
            raise NotFoundError(message)
        elif status_code == 422:
            errors = error_data.get("error", {}).get("details", [])
            raise ValidationError(message, errors=errors)
        elif status_code == 429:
            raise RateLimitError(message)
        elif status_code >= 500:
            raise ServerError(message)
        else:
            raise HebbrixError(message, status_code=status_code)

    async def request(
        self,
        method: str,
        path: str,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Make an HTTP request.

        Args:
            method: HTTP method (GET, POST, etc.)
            path: API path
            **kwargs: Additional arguments for httpx

        Returns:
            Response data as dictionary

        Raises:
            HebbrixError: On API errors
        """
        url = f"{self.base_url}{path}"

        response = await self._client.request(method, url, **kwargs)

        if response.status_code >= 400:
            self._handle_error(response)

        return response.json() if response.text else {}

    async def get(self, path: str, **kwargs) -> Dict[str, Any]:
        """Make a GET request."""
        return await self.request("GET", path, **kwargs)

    async def post(self, path: str, **kwargs) -> Dict[str, Any]:
        """Make a POST request."""
        return await self.request("POST", path, **kwargs)

    async def patch(self, path: str, **kwargs) -> Dict[str, Any]:
        """Make a PATCH request."""
        return await self.request("PATCH", path, **kwargs)

    async def delete(self, path: str, **kwargs) -> Dict[str, Any]:
        """Make a DELETE request."""
        return await self.request("DELETE", path, **kwargs)

    # Convenience methods
    async def search(
        self,
        query: str,
        collection_id: Optional[str] = None,
        limit: int = 10,
        search_type: str = "hybrid",
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Search memories.

        Args:
            query: Search query
            collection_id: Optional collection filter
            limit: Number of results
            search_type: Type of search (hybrid, vector, bm25, graph)
            filters: Additional filters

        Returns:
            List of search results
        """
        return await self.search_resource.search(
            query=query,
            collection_id=collection_id,
            limit=limit,
            search_type=search_type,
            filters=filters or {},
        )

    async def search_with_proof(
        self,
        query: str,
        collection_id: Optional[str] = None,
        limit: int = 10,
        search_type: str = "hybrid",
        filters: Optional[Dict[str, Any]] = None,
        user_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Search and return both results and the automatic ProofLoop context."""

        return await self.search_resource.search_with_proof(
            query=query,
            collection_id=collection_id,
            limit=limit,
            search_type=search_type,
            filters=filters or {},
            user_id=user_id,
        )

    async def reason(
        self,
        query: str,
        collection_id: Optional[str] = None,
        provider: Optional[str] = None,
        include_steps: bool = False,
    ) -> Dict[str, Any]:
        """
        Perform reasoning over memories.

        Args:
            query: Question or query
            collection_id: Optional collection filter
            provider: LLM provider (gemini, openai, anthropic)
            include_steps: Include reasoning steps

        Returns:
            Reasoning result with answer and sources
        """
        return await self.search_resource.reason(
            query=query,
            collection_id=collection_id,
            provider=provider,
            include_steps=include_steps,
        )

    async def close(self):
        """Close the HTTP client."""
        await self._client.aclose()

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()
