"""
Hebbrix Client

Main client class for interacting with the Hebbrix api.
"""

import os
from typing import Any, Dict, List, Optional

import httpx
from hebbrix.exceptions import (
    AuthenticationError,
    EntitlementError,
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
    CorrectionsResource,
    MemoriesResource,
    MemoryJobsResource,
    MemoryToolsResource,
    ProceduralResource,
    ProofLoopResource,
    RLResource,
    SearchResource,
    TemporalResource,
    WorkingMemoryResource,
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
        self.memory_jobs = MemoryJobsResource(self)
        self.corrections = CorrectionsResource(self)
        self.search_resource = SearchResource(self)
        self.proofloop = ProofLoopResource(self)
        self.rl = RLResource(self)
        self.procedural = ProceduralResource(self)
        self.temporal = TemporalResource(self)
        self.working_memory = WorkingMemoryResource(self)
        self.consolidation = ConsolidationResource(self)
        self.memory_tools = MemoryToolsResource(self)

    def _get_headers(self) -> Dict[str, str]:
        """Get request headers."""
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "hebbrix-python/2.5.0",
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
        except Exception:
            error_data = {}

        envelope = error_data.get("error") or error_data.get("detail") or {}
        if not isinstance(envelope, dict):
            envelope = {"message": str(envelope)}
        nested = envelope.get("message")
        details = nested if isinstance(nested, dict) else envelope
        message = (
            (details.get("message") if isinstance(details, dict) else None)
            or (nested if isinstance(nested, str) else None)
            or response.text
        )
        code = str(details.get("code") or envelope.get("code") or "") or None
        request_id = (
            details.get("request_id")
            or envelope.get("request_id")
            or response.headers.get("X-Request-ID")
        )

        if status_code == 401:
            raise AuthenticationError(
                message, code=code, request_id=request_id, details=details
            )
        elif status_code == 404:
            raise NotFoundError(
                message, code=code, request_id=request_id, details=details
            )
        elif status_code == 422:
            errors = error_data.get("error", {}).get("details", [])
            raise ValidationError(
                message,
                errors=errors,
                code=code,
                request_id=request_id,
                details=details,
            )
        elif status_code == 429:
            raise RateLimitError(
                message, code=code, request_id=request_id, details=details
            )
        elif status_code >= 500:
            raise ServerError(
                message, code=code, request_id=request_id, details=details
            )
        elif status_code in {402, 403} and (
            "ENTITLEMENT" in str(code or "")
            or details.get("error")
            in {"feature_not_available", "tier_upgrade_required"}
        ):
            raise EntitlementError(
                message,
                status_code=status_code,
                code=code,
                request_id=request_id,
                details=details,
            )
        else:
            raise HebbrixError(
                message,
                status_code=status_code,
                code=code,
                request_id=request_id,
                details=details,
            )

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

        payload = response.json() if response.text else {}
        if isinstance(payload, dict):
            # Preserve transport-only recovery identifiers on durable 202
            # receipts.  The resource layer needs these values if its local
            # readiness deadline expires after the write has committed.
            recovery_headers = {
                "request_id": response.headers.get("X-Request-ID"),
                "status_url": response.headers.get("Location"),
                "outbox_event_id": response.headers.get("X-Hebbrix-Index-Event"),
                "retry_after": response.headers.get("Retry-After"),
            }
            for key, value in recovery_headers.items():
                if value and not payload.get(key):
                    payload[key] = value
            replay = response.headers.get("X-Idempotent-Replay")
            if replay is not None and "idempotency_replay" not in payload:
                payload["idempotency_replay"] = replay.casefold() == "true"
        return payload

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
        user_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        run_id: Optional[str] = None,
        fast: Optional[bool] = None,
        threshold: Optional[float] = None,
        include_low_confidence: bool = False,
        group_by_source: bool = True,
        debug: bool = False,
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
            user_id=user_id,
            agent_id=agent_id,
            run_id=run_id,
            fast=fast,
            threshold=threshold,
            include_low_confidence=include_low_confidence,
            group_by_source=group_by_source,
            debug=debug,
        )

    async def search_with_proof(
        self,
        query: str,
        collection_id: Optional[str] = None,
        limit: int = 10,
        search_type: str = "hybrid",
        filters: Optional[Dict[str, Any]] = None,
        user_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        run_id: Optional[str] = None,
        fast: Optional[bool] = None,
        threshold: Optional[float] = None,
        include_low_confidence: bool = False,
        group_by_source: bool = True,
        debug: bool = False,
    ) -> Dict[str, Any]:
        """Search and return both results and the automatic ProofLoop context."""

        return await self.search_resource.search_with_proof(
            query=query,
            collection_id=collection_id,
            limit=limit,
            search_type=search_type,
            filters=filters or {},
            user_id=user_id,
            agent_id=agent_id,
            run_id=run_id,
            fast=fast,
            threshold=threshold,
            include_low_confidence=include_low_confidence,
            group_by_source=group_by_source,
            debug=debug,
        )

    async def reason(
        self,
        query: str,
        collection_id: Optional[str] = None,
        provider: Optional[str] = None,
        include_steps: bool = False,
        user_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        run_id: Optional[str] = None,
        facets: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Perform reasoning over memories.

        Args:
            query: Question or query
            collection_id: Optional collection filter
            provider: LLM provider (gemini, openai, anthropic)
            include_steps: Include reasoning steps
            user_id: End-user isolation scope
            agent_id: Agent isolation scope
            run_id: Run isolation scope
            facets: Optional typed decomposition facets

        Returns:
            Reasoning result with answer and sources
        """
        return await self.search_resource.reason(
            query=query,
            collection_id=collection_id,
            provider=provider,
            include_steps=include_steps,
            user_id=user_id,
            agent_id=agent_id,
            run_id=run_id,
            facets=facets,
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
