"""
API Resource classes

Each resource class wraps a specific set of API endpoints.
"""

import asyncio
import json
import time
import uuid
from typing import TYPE_CHECKING, Any, AsyncIterator, Dict, List, Optional
from urllib.parse import quote

from hebbrix.exceptions import IndexingTimeoutError
from hebbrix.models import SearchSafetyEnvelope

if TYPE_CHECKING:
    from hebbrix.client import MemoryClient


class BaseResource:
    """Base class for API resources."""

    def __init__(self, client: "MemoryClient"):
        self.client = client


def _memory_create_payload(
    *,
    collection_id: Optional[str] = None,
    content: Optional[str] = None,
    messages: Optional[List[Dict[str, str]]] = None,
    importance: Optional[float] = None,
    source_type: str = "text",
    source_reference: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    infer: bool = False,
    user_id: Optional[str] = None,
    agent_id: Optional[str] = None,
    run_id: Optional[str] = None,
    app_id: Optional[str] = None,
    namespace: Optional[str] = None,
    wait_for_index: bool = False,
    async_dispatch: Optional[bool] = None,
    title: Optional[str] = None,
    tags: Optional[List[str]] = None,
    source: Optional[str] = None,
) -> Dict[str, Any]:
    """Build the identical GA request body for sync and async clients."""

    if (content is None or not str(content).strip()) and not messages:
        raise ValueError("content or messages must be provided")
    payload: Dict[str, Any] = {
        "source_type": source_type,
        "metadata": metadata or {},
        "infer": infer,
        "wait_for_index": wait_for_index,
    }
    if content is not None:
        payload["content"] = content
    if messages is not None:
        payload["messages"] = messages
    optional_fields = {
        "collection_id": collection_id,
        "source_reference": source_reference,
        "user_id": user_id,
        "agent_id": agent_id,
        "run_id": run_id,
        "app_id": app_id,
        "namespace": namespace,
        "async_dispatch": async_dispatch,
        "title": title,
        "tags": tags,
        "source": source,
    }
    payload.update(
        {key: value for key, value in optional_fields.items() if value is not None}
    )
    if importance is not None:
        payload["importance"] = importance
    return payload


_SEARCH_SAFETY_FIELDS = frozenset(
    {
        "no_match",
        "abstain_recommended",
        "query_confidence",
        "grounding",
        "evidence_ids",
        "safety_contract_version",
    }
)


def _canonical_search_envelope(
    response: Dict[str, Any], *, rows_key: str = "results"
) -> Dict[str, Any]:
    """Validate API-owned evidence metadata and fail closed on contract drift."""

    data = dict(response) if isinstance(response, dict) else {}
    raw_rows = data.get(rows_key)
    rows = raw_rows if isinstance(raw_rows, list) else []
    missing = sorted(_SEARCH_SAFETY_FIELDS.difference(data))
    reason: Optional[str] = None
    confidence = data.get("query_confidence")
    if missing:
        reason = f"missing_safety_fields:{','.join(missing)}"
    elif not isinstance(data.get("no_match"), bool) or not isinstance(
        data.get("abstain_recommended"), bool
    ):
        reason = "invalid_abstention_fields"
    elif not isinstance(confidence, (int, float)) or isinstance(confidence, bool):
        reason = "invalid_query_confidence"
    elif not 0.0 <= float(confidence) <= 1.0:
        reason = "invalid_query_confidence"
    elif not isinstance(data.get("grounding"), dict):
        reason = "invalid_grounding_receipt"
    elif not isinstance(data.get("evidence_ids"), list):
        reason = "invalid_evidence_ids"
    elif data.get("safety_contract_version") != "search-safety-v1":
        reason = "unsupported_safety_contract_version"
    elif not isinstance(raw_rows, list):
        reason = "invalid_evidence_rows"
    elif any(
        not isinstance(value, str) or not value.strip()
        for value in data["evidence_ids"]
    ):
        reason = "invalid_evidence_ids"
    elif len(set(data["evidence_ids"])) != len(data["evidence_ids"]):
        reason = "duplicate_evidence_ids"
    elif any(
        not isinstance(row, dict)
        or not isinstance(row.get("memory_id", row.get("id")), str)
        or not row.get("memory_id", row.get("id", "")).strip()
        or ("memory_id" in row and "id" in row and row["memory_id"] != row["id"])
        for row in rows
    ):
        reason = "invalid_evidence_row_identity"
    elif not rows and data.get("no_match") is False:
        reason = "no_evidence_rows"
    else:
        row_ids = {
            str(row.get("memory_id") or row.get("id"))
            for row in rows
            if isinstance(row, dict) and (row.get("memory_id") or row.get("id"))
        }
        evidence_ids = {str(value) for value in data.get("evidence_ids", []) if value}
        if not row_ids.issubset(evidence_ids):
            reason = "rows_not_bound_to_evidence_ids"
        elif data.get("no_match") and (row_ids or evidence_ids):
            reason = "no_match_contains_evidence"

    # Degradation and abstention are confidence signals, not proof that the
    # API returned no evidence.  Erasing valid, evidence-bound rows here made
    # the SDK disagree with the REST response and converted a safe fallback
    # into a false negative.  Fail closed only when the envelope is malformed
    # or the server explicitly reports no match.
    if reason or data.get("no_match") is True:
        data[rows_key] = []
        if rows_key == "results":
            data["total"] = 0
        data["no_match"] = True
        data["abstain_recommended"] = True
        data["query_confidence"] = 0.0
        data["evidence_ids"] = []
        data["evidence_claims"] = []
        if rows_key == "sources":
            data["answer"] = None
            data["citations"] = []
        if reason:
            data["sdk_safety_reason"] = reason
            data["grounding"] = {
                "status": "no_grounded_match",
                "reason": reason,
            }
    elif data.get("degraded") is True or data.get("abstain_recommended") is True:
        data["sdk_safety_reason"] = "degraded_evidence_preserved"
    return data


class AuthResource(BaseResource):
    """Authentication endpoints."""

    async def register(
        self,
        email: str,
        password: str,
        full_name: str,
    ) -> Dict[str, Any]:
        """
        Register a new user.

        Args:
            email: User email
            password: User password
            full_name: User's full name

        Returns:
            Authentication response with access token
        """
        return await self.client.post(
            "/v1/auth/register",
            json={
                "email": email,
                "password": password,
                "full_name": full_name,
            },
        )

    async def login(self, email: str, password: str) -> Dict[str, Any]:
        """
        Login with email and password.

        Args:
            email: User email
            password: User password

        Returns:
            Authentication response with access token
        """
        return await self.client.post(
            "/v1/auth/login",
            json={"email": email, "password": password},
        )

    async def create_api_key(self, name: str) -> Dict[str, Any]:
        """
        Create a new API key.

        Args:
            name: API key name

        Returns:
            API key data (key is only shown once)
        """
        return await self.client.post(
            "/v1/auth/api-keys",
            json={"name": name},
        )

    async def get_me(self) -> Dict[str, Any]:
        """
        Get current user information.

        Returns:
            User data
        """
        return await self.client.get("/v1/auth/me")


class CollectionsResource(BaseResource):
    """Collection management endpoints."""

    async def create(
        self,
        name: str,
        description: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Create a new collection.

        Args:
            name: Collection name
            description: Optional description
            metadata: Optional metadata

        Returns:
            Created collection
        """
        return await self.client.post(
            "/v1/collections",
            json={
                "name": name,
                "description": description,
                "metadata": metadata or {},
            },
        )

    async def list(
        self,
        limit: int = 50,
        cursor: Optional[str] = None,
        name: Optional[str] = None,
        name_prefix: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        List all collections.

        Args:
            limit: Maximum number of items

        Returns:
            List of collections
        """
        page = await self.list_page(
            limit=limit,
            cursor=cursor,
            name=name,
            name_prefix=name_prefix,
        )
        return list(page.get("items") or [])

    async def list_page(
        self,
        limit: int = 50,
        cursor: Optional[str] = None,
        name: Optional[str] = None,
        name_prefix: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Return one canonical cursor-paginated collection page."""

        return await self.client.get(
            "/v1/collections",
            params={
                "cursor": cursor,
                "limit": limit,
                "name": name,
                "name_prefix": name_prefix,
            },
        )

    async def get(self, collection_id: str) -> Dict[str, Any]:
        """
        Get a specific collection.

        Args:
            collection_id: Collection ID

        Returns:
            Collection data
        """
        return await self.client.get(f"/v1/collections/{collection_id}")

    async def update(
        self,
        collection_id: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Update a collection.

        Args:
            collection_id: Collection ID
            name: New name
            description: New description
            metadata: New metadata

        Returns:
            Updated collection
        """
        data = {}
        if name is not None:
            data["name"] = name
        if description is not None:
            data["description"] = description
        if metadata is not None:
            data["metadata"] = metadata

        return await self.client.patch(
            f"/v1/collections/{collection_id}",
            json=data,
        )

    async def delete(self, collection_id: str) -> None:
        """
        Delete a collection.

        Args:
            collection_id: Collection ID
        """
        await self.client.delete(f"/v1/collections/{collection_id}")


class MemoriesResource(BaseResource):
    """Memory management endpoints."""

    async def create(
        self,
        collection_id: Optional[str] = None,
        content: Optional[str] = None,
        messages: Optional[List[Dict[str, str]]] = None,
        importance: Optional[float] = None,
        source_type: str = "text",
        source_reference: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        infer: bool = False,
        user_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        run_id: Optional[str] = None,
        app_id: Optional[str] = None,
        namespace: Optional[str] = None,
        wait_for_index: bool = False,
        async_dispatch: Optional[bool] = None,
        title: Optional[str] = None,
        tags: Optional[List[str]] = None,
        source: Optional[str] = None,
        idempotency_key: Optional[str] = None,
        index_timeout: float = 60.0,
        index_poll_interval: float = 0.5,
    ) -> Dict[str, Any]:
        """
        Create a memory.

        By default (``infer=False``) the content is stored verbatim as a single
        memory and the response's ``results[0].id`` is that memory's real,
        immediately-resolvable id — so ``create()`` round-trips with ``get()``.

        Behavior change (SDK 2.1.0): previously ``create()`` implicitly used the
        server's LLM extract-and-resolve path (``infer=true``), which rewrote the
        content, could emit zero or several fact rows, and — when the server ran
        extraction asynchronously — returned a transient job id that ``get()``
        could not resolve. That transient id is why a create/get round-trip
        failed. Storing verbatim by default makes the returned id stable.

        Pass ``infer=True`` to opt into fact extraction (``POST /v1/memories``
        with server-side inference). In that mode ``results`` may contain several
        extracted-fact ids, or the response may be ``{"job_id": ...}`` if the
        server extracts asynchronously — poll that job rather than treating it as
        a memory id.

        Args:
            collection_id: Optional collection ID. The server can resolve a
                default or app/namespace collection when omitted.
            content: Optional memory content.
            messages: Optional conversation messages (role/content) for the
                inference path. Either ``content`` or ``messages`` is required.
            importance: Importance (0-1). When set, the direct-store path
                (``infer=False``) uses this EXACT value. Leave as ``None`` to let
                the server auto-score. Ignored when ``infer=True``.
            source_type: Type of source
            source_reference: Reference to source
            metadata: Optional metadata
            infer: When True, extract facts via the LLM pipeline instead of
                storing ``content`` verbatim. Default False (direct store).
            user_id: End-user isolation scope.
            agent_id: Optional agent isolation scope.
            run_id: Optional run isolation scope.
            app_id: App-specific collection resolution key.
            namespace: Namespace within ``app_id``.
            wait_for_index: Wait for read-after-write searchability.
            async_dispatch: For inference, return a background job immediately.
            title: Optional source title.
            tags: Optional source tags.
            source: Optional source label.
            idempotency_key: Stable retry key. Reusing it with a different
                payload is rejected by the API.

        Returns:
            Created memory (MemoryAddResponse). With ``infer=False`` (default),
            ``results[0].id`` is the real, get-able memory id.
        """
        payload = _memory_create_payload(
            collection_id=collection_id,
            content=content,
            messages=messages,
            importance=importance,
            source_type=source_type,
            source_reference=source_reference,
            metadata=metadata,
            infer=infer,
            user_id=user_id,
            agent_id=agent_id,
            run_id=run_id,
            app_id=app_id,
            namespace=namespace,
            wait_for_index=wait_for_index,
            async_dispatch=async_dispatch,
            title=title,
            tags=tags,
            source=source,
        )
        request_kwargs: Dict[str, Any] = {"json": payload}
        if idempotency_key:
            request_kwargs["headers"] = {"Idempotency-Key": idempotency_key}
        receipt = await self.client.post("/v1/memories", **request_kwargs)
        if wait_for_index:
            receipt = await self._ensure_searchable_receipt(
                receipt,
                timeout=index_timeout,
                poll_interval=index_poll_interval,
                idempotency_key=idempotency_key,
            )
        return receipt

    async def create_batch(
        self,
        memories: List[Dict[str, Any]],
        *,
        collection_id: Optional[str] = None,
        user_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        run_id: Optional[str] = None,
        app_id: Optional[str] = None,
        namespace: Optional[str] = None,
        wait_for_index: bool = False,
        idempotency_key: Optional[str] = None,
        index_timeout: float = 60.0,
        index_poll_interval: float = 0.5,
    ) -> Dict[str, Any]:
        """Create a durable batch with explicit synchronous/async readiness.

        When ``wait_for_index`` is true, the API may return a durable 202
        receipt. The SDK polls the receipt until all items are searchable or
        raises ``IndexingTimeoutError`` carrying the original durable receipt.
        """

        if not 1 <= len(memories) <= 100:
            raise ValueError("memories must contain between 1 and 100 items")
        if any(not str(item.get("content") or "").strip() for item in memories):
            raise ValueError("every batch memory must contain non-empty content")
        payload = {
            "memories": memories,
            "wait_for_index": wait_for_index,
        }
        optional = {
            "collection_id": collection_id,
            "user_id": user_id,
            "agent_id": agent_id,
            "run_id": run_id,
            "app_id": app_id,
            "namespace": namespace,
        }
        payload.update(
            {key: value for key, value in optional.items() if value is not None}
        )
        kwargs: Dict[str, Any] = {"json": payload}
        if idempotency_key:
            kwargs["headers"] = {"Idempotency-Key": idempotency_key}
        receipt = await self.client.post("/v1/memories/batch", **kwargs)
        if wait_for_index and not (
            receipt.get("searchable") is True
            and str(receipt.get("processing_status") or "").casefold() == "completed"
        ):
            receipt = await self.wait_batch_until_searchable(
                receipt,
                timeout=index_timeout,
                poll_interval=index_poll_interval,
                idempotency_key=idempotency_key,
            )
        return receipt

    async def wait_batch_until_searchable(
        self,
        receipt: Dict[str, Any],
        *,
        timeout: float = 60.0,
        poll_interval: float = 0.5,
        idempotency_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Poll every item in an asynchronous batch receipt to one terminal state.

        Cancellation uses normal asyncio task cancellation. A failed/cancelled
        item or a local deadline raises explicitly; a successful return means
        every batch item reported ``searchable=true``.
        """

        memory_ids = list(dict.fromkeys(map(str, receipt.get("memory_ids") or [])))
        if not memory_ids:
            raise ValueError("batch receipt does not contain memory_ids")
        deadline = time.monotonic() + max(0.0, timeout)
        while True:
            rows = await asyncio.gather(
                *(self.get(memory_id) for memory_id in memory_ids)
            )
            for row in rows:
                state = str(row.get("processing_status") or "").casefold()
                if state == "completed" and row.get("searchable") is not True:
                    raise RuntimeError(
                        f"memory {row.get('id')} reported completed without "
                        "searchable=true"
                    )
                if state in {"failed", "cancelled", "canceled"}:
                    raise RuntimeError(
                        f"memory {row.get('id')} indexing reached terminal state {state}"
                    )
            if all(
                row.get("searchable") is True
                and str(row.get("processing_status") or "").casefold() == "completed"
                for row in rows
            ):
                return {
                    **receipt,
                    "processing_status": "completed",
                    "searchable": True,
                    "results": [
                        {
                            "id": memory_id,
                            "memory_id": memory_id,
                            "processing_status": "completed",
                        }
                        for memory_id in memory_ids
                    ],
                }
            if time.monotonic() >= deadline:
                timeout_error = TimeoutError(
                    f"batch was not searchable within {timeout}s; the write is durable",
                )
                raise IndexingTimeoutError(
                    str(timeout_error),
                    receipt,
                    idempotency_key=idempotency_key,
                ) from timeout_error
            await asyncio.sleep(max(0.05, poll_interval))

    async def wait_until_searchable(
        self,
        memory_id: str,
        *,
        timeout: float = 60.0,
        poll_interval: float = 0.5,
    ) -> Dict[str, Any]:
        """Poll the authoritative memory status until indexing is terminal."""

        deadline = time.monotonic() + max(0.0, timeout)
        while True:
            memory = await self.get(memory_id)
            state = str(memory.get("processing_status") or "").casefold()
            if memory.get("searchable") is True:
                return memory
            if state == "completed":
                raise RuntimeError(
                    f"memory {memory_id} reported completed without searchable=true"
                )
            if state in {"failed", "cancelled", "canceled"}:
                raise RuntimeError(
                    f"memory {memory_id} indexing reached terminal state {state}"
                )
            if time.monotonic() >= deadline:
                raise TimeoutError(
                    f"memory {memory_id} was not searchable within {timeout}s"
                )
            await asyncio.sleep(max(0.05, poll_interval))

    async def _ensure_searchable_receipt(
        self,
        receipt: Dict[str, Any],
        *,
        timeout: float,
        poll_interval: float,
        idempotency_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        if (
            receipt.get("searchable") is True
            and str(receipt.get("processing_status") or "").casefold() == "completed"
        ):
            return receipt
        job_id = str(receipt.get("job_id") or "")
        if job_id:
            deadline = time.monotonic() + max(0.0, timeout)
            while True:
                job = await self.client.get(f"/v1/memory-jobs/{job_id}")
                state = str(job.get("status") or "").casefold()
                if state == "completed":
                    receipt.update(job)
                    receipt["searchable"] = True
                    receipt["processing_status"] = "completed"
                    return receipt
                if state in {"failed", "cancelled", "canceled"}:
                    raise RuntimeError(
                        f"memory job {job_id} reached terminal state {state}"
                    )
                if time.monotonic() >= deadline:
                    timeout_error = TimeoutError(
                        f"memory job {job_id} did not become searchable within {timeout}s"
                    )
                    raise IndexingTimeoutError(
                        f"{timeout_error}; the write is durable",
                        receipt,
                        idempotency_key=idempotency_key,
                    ) from timeout_error
                await asyncio.sleep(max(0.05, poll_interval))

        candidates = [
            receipt.get("id"),
            *(
                item.get("id") or item.get("memory_id")
                for item in (receipt.get("results") or [])
                if isinstance(item, dict)
            ),
        ]
        memory_id = next((str(value) for value in candidates if value), "")
        if not memory_id:
            raise RuntimeError(
                "wait_for_index response contained neither a memory id nor a job id"
            )
        try:
            ready = await self.wait_until_searchable(
                memory_id,
                timeout=timeout,
                poll_interval=poll_interval,
            )
        except TimeoutError as exc:
            raise IndexingTimeoutError(
                f"memory {memory_id} was not searchable within {timeout}s; "
                "the write is durable",
                receipt,
                idempotency_key=idempotency_key,
            ) from exc
        receipt["searchable"] = True
        receipt["processing_status"] = "completed"
        receipt["status_url"] = ready.get("status_url") or f"/v1/memories/{memory_id}"
        return receipt

    async def list_page(
        self,
        collection_id: Optional[str] = None,
        cursor: Optional[str] = None,
        limit: int = 50,
        user_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        run_id: Optional[str] = None,
        scope: Optional[str] = None,
        include_superseded: bool = False,
    ) -> Dict[str, Any]:
        """
        List memories with full pagination metadata.

        Returns the raw cursor-paginated response from the backend so callers
        can iterate pages explicitly.

        Args:
            collection_id: Optional collection filter
            cursor: Opaque cursor from a previous page (None for the first page)
            limit: Page size (backend max: 100)

        Returns:
            Dict with keys:
              - items: List[Dict[str, Any]] — memories in this page
              - next_cursor: Optional[str] — pass to the next call to continue
              - has_more: bool — True if more pages exist
              - total_count: int — total number of memories matching the filter
        """
        params: Dict[str, Any] = {
            "limit": limit,
            "user_id": user_id,
            "agent_id": agent_id,
            "run_id": run_id,
            "scope": scope,
            "include_superseded": include_superseded,
        }
        if collection_id:
            params["collection_id"] = collection_id
        if cursor:
            params["cursor"] = cursor

        return await self.client.get(
            "/v1/memories",
            params={key: value for key, value in params.items() if value is not None},
        )

    async def list(
        self,
        collection_id: Optional[str] = None,
        cursor: Optional[str] = None,
        limit: int = 50,
        user_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        run_id: Optional[str] = None,
        scope: Optional[str] = None,
        include_superseded: bool = False,
    ) -> List[Dict[str, Any]]:
        """
        List memories (single page, items only).

        Back-compat convenience that drops pagination metadata. For
        page-at-a-time access use `list_page`; for iteration across all
        pages use `iter_all`.

        Args:
            collection_id: Optional collection filter
            cursor: Opaque cursor from a previous page
            limit: Page size (backend max: 100)

        Returns:
            List of memory dicts for the requested page
        """
        page = await self.list_page(
            collection_id=collection_id,
            cursor=cursor,
            limit=limit,
            user_id=user_id,
            agent_id=agent_id,
            run_id=run_id,
            scope=scope,
            include_superseded=include_superseded,
        )
        return page.get("items", [])

    async def iter_all(
        self,
        collection_id: Optional[str] = None,
        limit: int = 50,
        user_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        run_id: Optional[str] = None,
        scope: Optional[str] = None,
        include_superseded: bool = False,
    ) -> AsyncIterator[Dict[str, Any]]:
        """
        Async-iterate every memory matching the filter, following cursors.

        Example:
            async for memory in client.memories.iter_all(collection_id="col_x"):
                print(memory["id"])

        Args:
            collection_id: Optional collection filter
            limit: Page size used under the hood (backend max: 100)

        Yields:
            Memory dicts, one per item, across all pages
        """
        cursor: Optional[str] = None
        while True:
            page = await self.list_page(
                collection_id=collection_id,
                cursor=cursor,
                limit=limit,
                user_id=user_id,
                agent_id=agent_id,
                run_id=run_id,
                scope=scope,
                include_superseded=include_superseded,
            )
            for item in page.get("items", []):
                yield item
            if not page.get("has_more") or not page.get("next_cursor"):
                break
            cursor = page["next_cursor"]

    async def get(self, memory_id: str) -> Dict[str, Any]:
        """
        Get a specific memory.

        Args:
            memory_id: Memory ID

        Returns:
            Memory data with metadata
        """
        return await self.client.get(f"/v1/memories/{memory_id}")

    async def update(
        self,
        memory_id: str,
        content: Optional[str] = None,
        importance: Optional[float] = None,
        metadata: Optional[Dict[str, Any]] = None,
        wait_for_index: Optional[bool] = None,
        index_timeout: float = 60.0,
        index_poll_interval: float = 0.5,
    ) -> Dict[str, Any]:
        """
        Update a memory.

        Args:
            memory_id: Memory ID
            content: New content
            importance: New importance
            metadata: New metadata

        Returns:
            Updated memory
        """
        data = {}
        if content is not None:
            data["content"] = content
        if importance is not None:
            data["importance"] = importance
        if metadata is not None:
            data["metadata"] = metadata
        if wait_for_index is not None:
            data["wait_for_index"] = wait_for_index

        receipt = await self.client.patch(f"/v1/memories/{memory_id}", json=data)
        if wait_for_index is True:
            receipt = {**receipt, "id": receipt.get("id") or memory_id}
            receipt = await self._ensure_searchable_receipt(
                receipt,
                timeout=index_timeout,
                poll_interval=index_poll_interval,
            )
        return receipt

    async def delete(self, memory_id: str) -> None:
        """
        Delete a memory.

        Args:
            memory_id: Memory ID
        """
        await self.client.delete(f"/v1/memories/{memory_id}")


class MemoryJobsResource(BaseResource):
    """Polling helpers for asynchronous memory processing receipts."""

    async def get(self, job_id: str) -> Dict[str, Any]:
        return await self.client.get(f"/v1/memory-jobs/{job_id}")

    async def wait(
        self,
        job_id: str,
        *,
        timeout: float = 60.0,
        poll_interval: float = 0.5,
    ) -> Dict[str, Any]:
        """Poll until a memory job is terminal or the local timeout expires."""

        deadline = time.monotonic() + max(0.0, timeout)
        while True:
            receipt = await self.get(job_id)
            state = str(receipt.get("status") or "").casefold()
            if state in {"completed", "failed", "cancelled", "canceled"}:
                return receipt
            if time.monotonic() >= deadline:
                raise TimeoutError(f"memory job {job_id} did not finish in {timeout}s")
            await asyncio.sleep(max(0.05, poll_interval))


class CorrectionsResource(BaseResource):
    """Tenant-scoped factual, preference, and procedural corrections."""

    async def create(
        self,
        *,
        corrected_content: str,
        correction_type: str = "preference",
        original_content: Optional[str] = None,
        context: Optional[str] = None,
        memory_id: Optional[str] = None,
        collection_id: Optional[str] = None,
        user_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        confidence: float = 1.0,
        metadata: Optional[Dict[str, Any]] = None,
        idempotency_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        payload = {
            "corrected_content": corrected_content,
            "correction_type": correction_type,
            "original_content": original_content,
            "context": context,
            "memory_id": memory_id,
            "collection_id": collection_id,
            "user_id": user_id,
            "agent_id": agent_id,
            "confidence": confidence,
            "metadata": metadata,
        }
        request_kwargs: Dict[str, Any] = {
            "json": {key: value for key, value in payload.items() if value is not None}
        }
        if idempotency_key:
            request_kwargs["headers"] = {"Idempotency-Key": idempotency_key}
        return await self.client.post("/v1/corrections", **request_kwargs)

    async def relevant(
        self,
        query: str,
        *,
        correction_type: Optional[str] = None,
        collection_id: Optional[str] = None,
        user_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        include_global: bool = False,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        params = {
            "query": query,
            "correction_type": correction_type,
            "collection_id": collection_id,
            "user_id": user_id,
            "agent_id": agent_id,
            "include_global": include_global,
            "limit": limit,
        }
        return await self.client.get(
            "/v1/corrections/relevant",
            params={key: value for key, value in params.items() if value is not None},
        )

    async def get(self, correction_id: str) -> Dict[str, Any]:
        return await self.client.get(f"/v1/corrections/{correction_id}")

    async def delete(self, correction_id: str) -> Dict[str, Any]:
        return await self.client.delete(f"/v1/corrections/{correction_id}")


class SearchResource(BaseResource):
    """Search and reasoning endpoints."""

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
            Search results
        """
        response = await self.search_with_proof(
            query=query,
            collection_id=collection_id,
            limit=limit,
            search_type=search_type,
            filters=filters,
            user_id=user_id,
            agent_id=agent_id,
            run_id=run_id,
            fast=fast,
            threshold=threshold,
            include_low_confidence=include_low_confidence,
            group_by_source=group_by_source,
            debug=debug,
        )
        return response["results"]

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
    ) -> SearchSafetyEnvelope:
        """Search and preserve the automatic ProofLoop context.

        The legacy ``search`` method still returns only the result list. Use
        this method when the selected evidence will feed a learned decision.
        """

        payload: Dict[str, Any] = {
            "query": query,
            "collection_id": collection_id,
            "user_id": user_id,
            "agent_id": agent_id,
            "run_id": run_id,
            "limit": limit,
            "search_type": search_type,
            "filters": filters or {},
            "include_low_confidence": include_low_confidence,
            "group_by_source": group_by_source,
            "debug": debug,
        }
        if fast is not None:
            payload["fast"] = fast
        if threshold is not None:
            payload["threshold"] = threshold
        response = await self.client.post(
            "/v1/search",
            json={key: value for key, value in payload.items() if value is not None},
        )
        return _canonical_search_envelope(response)

    async def similar(
        self,
        memory_id: str,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """
        Find similar memories.

        Args:
            memory_id: Memory ID
            limit: Number of results

        Returns:
            Similar memories
        """
        response = await self.client.get(
            f"/v1/search/similar/{memory_id}",
            params={"limit": limit},
        )

        return response.get("results", [])

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
    ) -> SearchSafetyEnvelope:
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
        response = await self.client.post(
            "/v1/search/reason",
            json={
                "query": query,
                "collection_id": collection_id,
                "provider": provider,
                "include_steps": include_steps,
                "user_id": user_id,
                "agent_id": agent_id,
                "run_id": run_id,
                "facets": facets or [],
            },
        )
        return _canonical_search_envelope(response, rows_key="sources")


class ProofLoopResource(BaseResource):
    """Outcome Memory decisions with automatic evidence and verifiable proofs."""

    async def decide(
        self,
        *,
        policy_key: str,
        candidates: List[Dict[str, Any]],
        proof_context: Optional[Any] = None,
        collection_id: Optional[str] = None,
        user_id: Optional[str] = None,
        idempotency_key: Optional[str] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        token = (
            proof_context.get("token")
            if isinstance(proof_context, dict)
            else proof_context
        )
        body = {
            "policy_key": policy_key,
            "candidates": candidates,
            "collection_id": collection_id,
            "user_id": user_id,
            "idempotency_key": idempotency_key,
            **kwargs,
        }
        if token:
            body["proof_context_token"] = token
        return await self.client.post("/v1/learning/decisions", json=body)

    async def register_verifier(
        self,
        *,
        policy_key: str,
        api_key_id: str,
        source_system: str,
        metric_keys: List[str],
        collection_id: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Owner-session administration; the agent cannot register its own verifier."""
        return await self.client.post(
            "/v1/learning/verifiers",
            json={
                "policy_key": policy_key,
                "api_key_id": api_key_id,
                "source_system": source_system,
                "metric_keys": metric_keys,
                "collection_id": collection_id,
                "user_id": user_id,
            },
        )

    async def revoke_verifier(self, verifier_id: str) -> Dict[str, Any]:
        """Revoke one source without deleting historical evidence."""
        return await self.client.post(
            f"/v1/learning/verifiers/{quote(verifier_id, safe='')}/revoke", json={}
        )

    async def create_episode(
        self,
        *,
        policy_key: str,
        verifier_id: str,
        idempotency_key: str,
        collection_id: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create a scoped durable episode; never grants execution permission."""
        return await self.client.post(
            "/v1/learning/episodes",
            json={
                "policy_key": policy_key,
                "verifier_id": verifier_id,
                "idempotency_key": idempotency_key,
                "collection_id": collection_id,
                "user_id": user_id,
            },
        )

    async def get_episode(self, episode_id: str, *, offset: int = 0) -> Dict[str, Any]:
        return await self.client.get(
            f"/v1/learning/episodes/{quote(episode_id, safe='')}",
            params={"offset": offset},
        )

    async def close_episode(self, episode_id: str, *, status: str) -> Dict[str, Any]:
        return await self.client.post(
            f"/v1/learning/episodes/{quote(episode_id, safe='')}/close",
            json={"status": status},
        )

    async def record_execution(
        self,
        decision_id: str,
        *,
        attempt_id: str,
        status: str,
        actual_action_key: str,
        arguments_digest: str,
        evidence_digest: Optional[str] = None,
        occurred_at: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Record an execution claim, not an instruction to execute."""
        body = {
            "attempt_id": attempt_id,
            "status": status,
            "actual_action_key": actual_action_key,
            "arguments_digest": arguments_digest,
        }
        if evidence_digest is not None:
            body["evidence_digest"] = evidence_digest
        if occurred_at is not None:
            body["occurred_at"] = occurred_at
        return await self.client.post(
            f"/v1/learning/decisions/{quote(decision_id, safe='')}/executions",
            json=body,
        )

    async def assessment(
        self, decision_id: str, *, evidence_offset: int = 0
    ) -> Dict[str, Any]:
        return await self.client.get(
            f"/v1/learning/decisions/{quote(decision_id, safe='')}/assessment",
            params={"evidence_offset": evidence_offset},
        )

    async def assess_experience(
        self, *, candidate: Dict[str, Any], context: Dict[str, Any],
        collection_id: Optional[str] = None, user_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Revalidate an experience hypothesis. Never grants execution permission."""
        return await self.client.post(
            "/v1/learning/experiences/assess",
            json={"candidate": candidate, "context": context,
                  "collection_id": collection_id, "user_id": user_id},
        )

    async def experience_context(
        self, *, memory_collection_id: str, policy_key: str,
        references: List[Dict[str, Any]], context: Dict[str, Any],
        evidence_collection_id: Optional[str] = None,
        user_id: Optional[str] = None, agent_id: Optional[str] = None,
        run_id: Optional[str] = None, max_context_bytes: int = 16000,
    ) -> Dict[str, Any]:
        """Revalidate stored hypotheses. The response is not execution permission."""
        return await self.client.post(
            "/v1/learning/experiences/context",
            json={
                "memory_collection_id": memory_collection_id,
                "evidence_collection_id": evidence_collection_id,
                "user_id": user_id, "agent_id": agent_id, "run_id": run_id,
                "policy_key": policy_key, "references": references,
                "context": context, "max_context_bytes": max_context_bytes,
            },
        )

    async def verifier_evidence(
        self, verifier_id: str, decision_id: str
    ) -> Dict[str, Any]:
        """Call with the dedicated verifier client, never the actor's credential."""
        return await self.client.get(
            f"/v1/learning/verifiers/{quote(verifier_id, safe='')}/decisions/{quote(decision_id, safe='')}"
        )

    async def deliver_verified_outcomes(
        self,
        verifier_id: str,
        *,
        decision_id: str,
        source_event_id: str,
        evidence_digest: str,
        execution_digest: str,
        observations: List[Dict[str, Any]],
        evidence_document: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Deliver independently checked observations using the registered source key."""
        return await self.client.post(
            f"/v1/learning/verifiers/{quote(verifier_id, safe='')}/events",
            json={
                "decision_id": decision_id,
                "source_event_id": source_event_id,
                "evidence_digest": evidence_digest,
                "execution_digest": execution_digest,
                "observations": observations,
                **({"evidence_document": evidence_document} if evidence_document is not None else {}),
            },
        )

    async def get_decision(self, decision_id: str) -> Dict[str, Any]:
        return await self.client.get(f"/v1/learning/decisions/{decision_id}")

    async def register_context_schema(
        self,
        policy_key: str,
        *,
        context_schema: Dict[str, Any],
        collection_id: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Enroll before any decisions; changing learning semantics needs a new policy."""
        return await self.client.request(
            "PUT",
            f"/v1/learning/policies/{quote(policy_key, safe='')}/context-schema",
            json={
                "context_schema": context_schema,
                "collection_id": collection_id,
                "user_id": user_id,
            },
        )

    async def context_schema(
        self,
        policy_key: str,
        *,
        collection_id: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        return await self.client.get(
            f"/v1/learning/policies/{quote(policy_key, safe='')}/context-schema",
            params={
                k: v
                for k, v in {"collection_id": collection_id, "user_id": user_id}.items()
                if v is not None
            },
        )

    async def setup_policy(self, policy_key: str, *, context_schema: Dict[str, Any],
                           actions: Dict[str, Any], collection_id: Optional[str] = None,
                           user_id: Optional[str] = None) -> Dict[str, Any]:
        """One atomic setup call. Risk/target/description are supplied by the owner.
        Only explicitly low-risk exploration_allowed actions learn by default.
        This neither permits execution nor changes an existing policy.
        """
        return await self.client.post(f"/v1/learning/policies/{quote(policy_key, safe='')}/setup",
            json=dict(collection_id=collection_id, user_id=user_id,
                context_schema=context_schema, configuration=dict(actions=actions)))

    async def learning_report(self, policy_key: str, *, days: int = 7,
                              collection_id: Optional[str] = None,
                              user_id: Optional[str] = None) -> Dict[str, Any]:
        """Bounded descriptive report, not a causal uplift or execution guarantee."""
        return await self.client.get(f"/v1/learning/policies/{quote(policy_key, safe='')}/report",
            params={k: v for k, v in dict(days=days, collection_id=collection_id,
                user_id=user_id).items() if v is not None})

    async def decide_with_advice(self, *, policy_key: str, candidates: List[Dict[str, Any]],
                                 context: Dict[str, Any], advisor,
                                 collection_id: Optional[str] = None,
                                 user_id: Optional[str] = None,
                                 idempotency_key: Optional[str] = None) -> Dict[str, Any]:
        """Read evidence, call your advisor once, then log its explicit choice.
        advisor must return chosen_action_key, action_probability and the complete
        behavior_probabilities. No model confidence is invented as a propensity.
        No tool execution or outcome is recorded by this helper.
        """
        card = await self.policy_advice(policy_key, context=context,
            collection_id=collection_id, user_id=user_id)
        selection = await advisor(card)
        if not isinstance(selection, dict) or set(selection) != {
            "chosen_action_key", "action_probability", "behavior_probabilities"}:
            raise ValueError("advisor must return the choice and its actual complete logging distribution")
        return await self.decide(policy_key=policy_key, candidates=candidates, context=context,
            collection_id=collection_id, user_id=user_id, idempotency_key=idempotency_key,
            mode="observe", **selection)

    async def configure_policy(self, policy_key: str, *, configuration: Dict[str, Any],
                               expected_revision: int = 0, collection_id: Optional[str] = None,
                               user_id: Optional[str] = None) -> Dict[str, Any]:
        """Explicit risk/strategy opt-in, revision-checked; not execution permission."""
        return await self.client.request("PUT",
            f"/v1/learning/policies/{quote(policy_key, safe='')}/configuration",
            json=dict(configuration=configuration, expected_revision=expected_revision,
                      collection_id=collection_id, user_id=user_id))

    async def policy_configuration(self, policy_key: str, *, collection_id: Optional[str] = None,
                                   user_id: Optional[str] = None) -> Dict[str, Any]:
        return await self.client.get(f"/v1/learning/policies/{quote(policy_key, safe='')}/configuration",
            params={k: v for k, v in dict(collection_id=collection_id, user_id=user_id).items() if v is not None})

    async def policy_advice(self, policy_key: str, *, context: Optional[Dict[str, Any]] = None,
                            collection_id: Optional[str] = None, user_id: Optional[str] = None) -> Dict[str, Any]:
        """Read caller-reported evidence and a candidate, never an execution permit."""
        return await self.client.get(f"/v1/learning/policies/{quote(policy_key, safe='')}/advice",
            params={k: v for k, v in dict(context=json.dumps(context or {}),
                collection_id=collection_id, user_id=user_id).items() if v is not None})

    async def action_advice(self, query: str, *, policy_key: str, action_key: str,
                           context: Optional[Dict[str, Any]] = None, collection_id: Optional[str] = None,
                           user_id: Optional[str] = None) -> Dict[str, Any]:
        """Read ASK/REVIEW/ACT advice for an exact configured action. ACT is not permission."""
        return await self.client.get("/v1/confidence", params={k: v for k, v in
            dict(query=query, policy_key=policy_key, action_key=action_key,
                 context=json.dumps(context or {}), collection_id=collection_id,
                 end_user_id=user_id).items() if v is not None})

    async def define_metric(
        self,
        *,
        policy_key: str,
        metric_key: str,
        name: str,
        min_value: float,
        max_value: float,
        collection_id: Optional[str] = None,
        user_id: Optional[str] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        return await self.client.post(
            "/v1/learning/metrics",
            json={
                "policy_key": policy_key,
                "metric_key": metric_key,
                "name": name,
                "min_value": min_value,
                "max_value": max_value,
                "collection_id": collection_id,
                "user_id": user_id,
                **kwargs,
            },
        )

    async def list_metrics(
        self,
        *,
        policy_key: Optional[str] = None,
        collection_id: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        params = {
            "policy_key": policy_key,
            "collection_id": collection_id,
            "user_id": user_id,
        }
        return await self.client.get(
            "/v1/learning/metrics",
            params={key: value for key, value in params.items() if value is not None},
        )

    async def policy_insights(
        self,
        policy_key: str,
        *,
        collection_id: Optional[str] = None,
        user_id: Optional[str] = None,
        action_keys: Optional[List[str]] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        params: Dict[str, Any] = {
            "collection_id": collection_id,
            "user_id": user_id,
            "action_key": action_keys,
            "context": json.dumps(context) if context is not None else None,
        }
        return await self.client.get(
            f"/v1/learning/policies/{policy_key}/insights",
            params={key: value for key, value in params.items() if value is not None},
        )

    async def evaluate_policy(
        self,
        policy_key: str,
        *,
        collection_id: Optional[str] = None,
        user_id: Optional[str] = None,
        limit: int = 5000,
    ) -> Dict[str, Any]:
        return await self.client.post(
            f"/v1/learning/policies/{policy_key}/evaluate",
            json={
                "collection_id": collection_id,
                "user_id": user_id,
                "limit": limit,
            },
        )

    async def record_outcome(
        self,
        decision_id: str,
        *,
        observations: Optional[List[Dict[str, Any]]] = None,
        reward: Optional[float] = None,
        success: Optional[bool] = None,
        idempotency_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        return await self.client.post(
            f"/v1/learning/decisions/{decision_id}/outcomes",
            json={
                "observations": observations or [],
                "reward": reward,
                "success": success,
                "idempotency_key": idempotency_key,
            },
        )

    async def proof(self, decision_id: str) -> Dict[str, Any]:
        return await self.client.get(f"/v1/learning/decisions/{decision_id}/proof")

    async def public_key(self, key_id: Optional[str] = None) -> Dict[str, Any]:
        params = {"key_id": key_id} if key_id else None
        return await self.client.get("/v1/learning/proof-key", params=params)


class RLResource(BaseResource):
    """Reinforcement Learning training endpoints."""

    async def train_memory_manager(
        self,
        num_episodes: int = 100,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Train the Memory Manager agent using RL.

        Args:
            num_episodes: Number of training episodes
            **kwargs: Additional training parameters

        Returns:
            Training results with metrics
        """
        return await self.client.post(
            "/v1/rl/train/memory-manager",
            json={
                "num_episodes": num_episodes,
                **kwargs,
            },
        )

    async def train_answer_agent(
        self,
        num_episodes: int = 100,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Train the Answer Agent using RL.

        Args:
            num_episodes: Number of training episodes
            **kwargs: Additional training parameters

        Returns:
            Training results with metrics
        """
        return await self.client.post(
            "/v1/rl/train/answer-agent",
            json={
                "num_episodes": num_episodes,
                **kwargs,
            },
        )

    async def get_metrics(self) -> Dict[str, Any]:
        """
        Get RL training metrics.

        Returns:
            Training metrics and statistics
        """
        return await self.client.get("/v1/rl/metrics")

    async def evaluate(
        self,
        agent_type: str,
        collection_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Evaluate a trained RL agent.

        Args:
            agent_type: Type of agent (memory_manager or answer_agent)
            collection_id: Optional collection to evaluate on

        Returns:
            Evaluation results
        """
        return await self.client.post(
            "/v1/rl/evaluate",
            json={
                "agent_type": agent_type,
                "collection_id": collection_id,
            },
        )


class ProceduralResource(BaseResource):
    """Procedural memory endpoints."""

    @staticmethod
    def _unwrap_procedure(response: Dict[str, Any]) -> Dict[str, Any]:
        procedure = response.get("procedure")
        if isinstance(procedure, dict):
            return procedure
        if response.get("procedure_id") and not response.get("id"):
            return {**response, "id": response["procedure_id"]}
        return response

    async def create(
        self,
        name: str,
        description: str,
        trigger_condition: str,
        action_sequence: List[str],
        collection_id: Optional[str] = None,
        category: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Create a new procedure.

        Args:
            name: Procedure name
            description: What the procedure does
            trigger_condition: When to trigger (IF condition)
            action_sequence: Steps to execute (THEN actions)
            collection_id: Optional collection ID
            category: Optional category
            metadata: Optional metadata

        Returns:
            Created procedure
        """
        response = await self.client.post(
            "/v1/procedures",
            json={
                "name": name,
                "description": description,
                "condition": {"expression": trigger_condition},
                "action": {"steps": action_sequence},
                "collection_id": collection_id,
                "category": category,
                "parameters": metadata or {},
            },
        )
        return self._unwrap_procedure(response)

    async def list(
        self,
        collection_id: Optional[str] = None,
        category: Optional[str] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """
        List procedures.

        Args:
            collection_id: Optional collection filter
            category: Optional category filter
            skip: Number of items to skip
            limit: Maximum number of items

        Returns:
            List of procedures
        """
        params = {"skip": skip, "limit": limit}
        if collection_id:
            params["collection_id"] = collection_id
        if category:
            params["category"] = category

        response = await self.client.get("/v1/procedures", params=params)
        return (
            response if isinstance(response, list) else response.get("procedures", [])
        )

    async def get(self, procedure_id: str) -> Dict[str, Any]:
        """
        Get a specific procedure.

        Args:
            procedure_id: Procedure ID

        Returns:
            Procedure data
        """
        response = await self.client.get(f"/v1/procedures/{procedure_id}")
        return self._unwrap_procedure(response)

    async def execute(
        self,
        procedure_id: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Execute a procedure.

        Args:
            procedure_id: Procedure ID
            context: Optional execution context

        Returns:
            Execution result
        """
        response = await self.client.post(
            f"/v1/procedures/{procedure_id}/execute",
            json={"input_state": context or {}},
        )
        result = response.get("execution_result")
        return result if isinstance(result, dict) else response

    async def update(
        self,
        procedure_id: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
        trigger_condition: Optional[str] = None,
        action_sequence: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Update a procedure.

        Args:
            procedure_id: Procedure ID
            name: New name
            description: New description
            trigger_condition: New trigger
            action_sequence: New actions
            metadata: New metadata

        Returns:
            Updated procedure
        """
        data = {}
        if name is not None:
            data["name"] = name
        if description is not None:
            data["description"] = description
        if trigger_condition is not None:
            data["condition"] = {"expression": trigger_condition}
        if action_sequence is not None:
            data["action"] = {"steps": action_sequence}
        if metadata is not None:
            data["parameters"] = metadata

        response = await self.client.patch(f"/v1/procedures/{procedure_id}", json=data)
        return self._unwrap_procedure(response)

    async def delete(self, procedure_id: str) -> None:
        """
        Delete a procedure.

        Args:
            procedure_id: Procedure ID
        """
        await self.client.delete(f"/v1/procedures/{procedure_id}")


class TemporalResource(BaseResource):
    """Temporal knowledge graph endpoints."""

    async def add_fact(
        self,
        subject: str,
        predicate: str,
        object: str,
        valid_from: str,
        valid_until: Optional[str] = None,
        observed_at: Optional[str] = None,
        subject_type: str = "ENTITY",
        object_type: str = "ENTITY",
        confidence: float = 1.0,
        source_memory_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Add a temporal fact to the knowledge graph.

        Args:
            subject: Subject entity
            predicate: Relationship type
            object: Object entity
            valid_from: When fact became true (ISO timestamp)
            valid_until: When fact stopped being true (ISO timestamp)
            confidence: Confidence score (0-1)
            source_memory_id: Source memory that introduced this fact
            metadata: Optional metadata

        Returns:
            Created fact
        """
        return await self.client.post(
            "/v1/temporal/facts",
            json={
                "subject": subject,
                "subject_type": subject_type,
                "predicate": predicate,
                "object": object,
                "object_type": object_type,
                "valid_from": valid_from,
                "valid_until": valid_until,
                "observed_at": observed_at,
                "confidence": confidence,
                "source_memory_id": source_memory_id,
                "metadata": metadata or {},
            },
        )

    async def query_facts(
        self,
        subject: Optional[str] = None,
        predicate: Optional[str] = None,
        object: Optional[str] = None,
        at_time: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Query temporal facts.

        Args:
            subject: Filter by subject
            predicate: Filter by predicate
            object: Filter by object
            at_time: Query facts valid at specific time (ISO timestamp)

        Returns:
            List of matching facts
        """
        if not subject:
            raise ValueError("subject is required by the temporal query contract")
        if at_time:
            response = await self.query_at_time(
                subject=subject,
                predicate=predicate,
                timestamp=at_time,
            )
            facts = list(response.get("facts") or [])
        elif predicate:
            response = await self.history(subject=subject, predicate=predicate)
            facts = list(response.get("history") or [])
        else:
            raise ValueError("predicate or at_time is required")
        if object is not None:
            facts = [row for row in facts if row.get("object") == object]
        return facts

    async def query_at_time(
        self,
        subject: str,
        timestamp: str,
        predicate: Optional[str] = None,
    ) -> Dict[str, Any]:
        return await self.client.post(
            "/v1/temporal/facts/query-at-time",
            json={"subject": subject, "predicate": predicate, "timestamp": timestamp},
        )

    async def history(
        self, subject: str, predicate: str, limit: int = 50
    ) -> Dict[str, Any]:
        return await self.client.get(
            "/v1/temporal/facts/history",
            params={"subject": subject, "predicate": predicate, "limit": limit},
        )

    async def conflicts(self, subject: str, predicate: str) -> Dict[str, Any]:
        return await self.client.get(
            "/v1/temporal/facts/conflicts",
            params={"subject": subject, "predicate": predicate},
        )

    async def invalidate(
        self, subject: str, predicate: str, object: str
    ) -> Dict[str, Any]:
        return await self.client.post(
            "/v1/temporal/facts/invalidate",
            json={"subject": subject, "predicate": predicate, "object": object},
        )

    async def point_in_time(
        self,
        timestamp: str,
        entity: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Query knowledge state at a specific point in time.

        Args:
            timestamp: ISO timestamp
            entity: Optional entity filter

        Returns:
            Knowledge state at that time
        """
        if not entity:
            raise ValueError("entity is required and maps to the canonical subject")
        return await self.query_at_time(subject=entity, timestamp=timestamp)

    async def delete_fact(self, fact_id: str) -> Dict[str, Any]:
        """Permanently delete a tenant-scoped temporal fact by stable ID."""

        return await self.client.delete(f"/v1/temporal/facts/{fact_id}")


class WorkingMemoryResource(BaseResource):
    """Working memory buffer endpoints."""

    def __init__(self, client: "MemoryClient"):
        super().__init__(client)
        self.session_id = f"sdk-{uuid.uuid4()}"

    async def add(
        self,
        role: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Add item to working memory buffer.

        Args:
            role: Role (user, assistant, system)
            content: Content
            metadata: Optional metadata

        Returns:
            Added item
        """
        return await self.client.post(
            "/v1/working-memory/add",
            json={
                "session_id": session_id or self.session_id,
                "role": role,
                "content": content,
                "metadata": metadata or {},
            },
        )

    async def get_context(
        self, session_id: Optional[str] = None, include_compressed: bool = False
    ) -> Dict[str, Any]:
        """
        Get current working memory context.

        Returns:
            Current context with buffer items
        """
        return await self.client.get(
            f"/v1/working-memory/context/{session_id or self.session_id}",
            params={"include_compressed": include_compressed},
        )

    async def compress(self, session_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Compress working memory buffer.

        Returns:
            Compression result
        """
        return await self.client.post(
            f"/v1/working-memory/compress/{session_id or self.session_id}"
        )

    async def clear(self, session_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Clear working memory buffer.

        Returns:
            Clear result
        """
        return await self.client.delete(
            f"/v1/working-memory/clear/{session_id or self.session_id}"
        )


class ConsolidationResource(BaseResource):
    """Memory consolidation endpoints."""

    async def consolidate(
        self,
        collection_id: str,
        lookback_days: int = 7,
        utility_threshold: float = 0.3,
    ) -> Dict[str, Any]:
        """
        Trigger memory consolidation.

        Args:
            collection_id: Collection to consolidate
            threshold: Minimum number of memories to consolidate

        Returns:
            Consolidation results
        """
        return await self.client.post(
            "/v1/consolidation/consolidate",
            json={
                "collection_id": collection_id,
                "lookback_days": lookback_days,
                "utility_threshold": utility_threshold,
            },
        )

    async def get_stats(self, collection_id: str) -> Dict[str, Any]:
        """
        Get consolidation statistics.

        Args:
            collection_id: Collection ID

        Returns:
            Consolidation stats
        """
        return await self.client.get(f"/v1/consolidation/stats/{collection_id}")


class MemoryToolsResource(BaseResource):
    """Self-editing memory tools endpoints."""

    async def replace(
        self,
        memory_id: str,
        new_content: str,
        reason: Optional[str] = None,
        *,
        old_content: Optional[str] = None,
        collection_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Replace memory content.

        Args:
            memory_id: Memory to replace
            new_content: New content
            reason: Optional reason for replacement

        Returns:
            Updated memory
        """
        if old_content is None or collection_id is None:
            raise ValueError("old_content and collection_id are required")
        return await self.client.post(
            "/v1/memory-tools/replace",
            json={
                "memory_id": memory_id,
                "old_content": old_content,
                "new_content": new_content,
                "collection_id": collection_id,
            },
        )

    async def insert(
        self,
        collection_id: str,
        content: str,
        position: Optional[int] = None,
        reason: Optional[str] = None,
        importance: float = 0.5,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Insert new memory at position.

        Args:
            collection_id: Collection ID
            content: Memory content
            position: Position to insert
            reason: Optional reason

        Returns:
            Inserted memory
        """
        compatibility = dict(metadata or {})
        if position is not None:
            compatibility.setdefault("requested_position", position)
        if reason is not None:
            compatibility.setdefault("reason", reason)
        return await self.client.post(
            "/v1/memory-tools/insert",
            json={
                "collection_id": collection_id,
                "content": content,
                "importance": importance,
                "metadata": compatibility,
            },
        )

    async def rethink(
        self,
        memory_id: str,
        collection_id: str,
        query: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Re-evaluate memory in light of new information.

        Args:
            memory_id: Memory to re-evaluate
            query: New context or question

        Returns:
            Re-evaluation result
        """
        return await self.client.post(
            "/v1/memory-tools/rethink",
            json={
                "memory_id": memory_id,
                "collection_id": collection_id,
            },
        )
