"""
API Resource classes

Each resource class wraps a specific set of API endpoints.
"""

from typing import TYPE_CHECKING, Any, AsyncIterator, Dict, List, Optional

if TYPE_CHECKING:
    from hebbrix.client import MemoryClient


class BaseResource:
    """Base class for API resources."""

    def __init__(self, client: "MemoryClient"):
        self.client = client


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
        skip: int = 0,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """
        List all collections.

        Args:
            skip: Number of items to skip
            limit: Maximum number of items

        Returns:
            List of collections
        """
        return await self.client.get(
            "/v1/collections",
            params={"skip": skip, "limit": limit},
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
        collection_id: str,
        content: str,
        importance: Optional[float] = None,
        source_type: str = "text",
        source_reference: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        infer: bool = False,
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
            collection_id: Collection ID
            content: Memory content
            importance: Importance (0-1). When set, the direct-store path
                (``infer=False``) uses this EXACT value. Leave as ``None`` to let
                the server auto-score. Ignored when ``infer=True``.
            source_type: Type of source
            source_reference: Reference to source
            metadata: Optional metadata
            infer: When True, extract facts via the LLM pipeline instead of
                storing ``content`` verbatim. Default False (direct store).

        Returns:
            Created memory (MemoryAddResponse). With ``infer=False`` (default),
            ``results[0].id`` is the real, get-able memory id.
        """
        payload: Dict[str, Any] = {
            "collection_id": collection_id,
            "content": content,
            "source_type": source_type,
            "source_reference": source_reference,
            "metadata": metadata or {},
            "infer": infer,
        }
        # Send importance ONLY when the caller set it, so an unspecified
        # importance keeps the server's auto-scoring instead of pinning a value.
        if importance is not None:
            payload["importance"] = importance
        return await self.client.post(
            "/v1/memories",
            json=payload,
        )

    async def list_page(
        self,
        collection_id: Optional[str] = None,
        cursor: Optional[str] = None,
        limit: int = 50,
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
        params: Dict[str, Any] = {"limit": limit}
        if collection_id:
            params["collection_id"] = collection_id
        if cursor:
            params["cursor"] = cursor

        return await self.client.get("/v1/memories", params=params)

    async def list(
        self,
        collection_id: Optional[str] = None,
        cursor: Optional[str] = None,
        limit: int = 50,
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
            collection_id=collection_id, cursor=cursor, limit=limit
        )
        return page.get("items", [])

    async def iter_all(
        self,
        collection_id: Optional[str] = None,
        limit: int = 50,
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
                collection_id=collection_id, cursor=cursor, limit=limit
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

        return await self.client.patch(f"/v1/memories/{memory_id}", json=data)

    async def delete(self, memory_id: str) -> None:
        """
        Delete a memory.

        Args:
            memory_id: Memory ID
        """
        await self.client.delete(f"/v1/memories/{memory_id}")


class SearchResource(BaseResource):
    """Search and reasoning endpoints."""

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
            Search results
        """
        response = await self.client.post(
            "/v1/search",
            json={
                "query": query,
                "collection_id": collection_id,
                "limit": limit,
                "search_type": search_type,
                "filters": filters or {},
            },
        )

        return response.get("results", [])

    async def search_with_proof(
        self,
        query: str,
        collection_id: Optional[str] = None,
        limit: int = 10,
        search_type: str = "hybrid",
        filters: Optional[Dict[str, Any]] = None,
        user_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Search and preserve the automatic ProofLoop context.

        The legacy ``search`` method still returns only the result list. Use
        this method when the selected evidence will feed a learned decision.
        """

        return await self.client.post(
            "/v1/search",
            json={
                "query": query,
                "collection_id": collection_id,
                "user_id": user_id,
                "limit": limit,
                "search_type": search_type,
                "filters": filters or {},
            },
        )

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
        return await self.client.post(
            "/v1/search/reason",
            json={
                "query": query,
                "collection_id": collection_id,
                "provider": provider,
                "include_steps": include_steps,
            },
        )


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
            **kwargs,
        }
        if token:
            body["proof_context_token"] = token
        return await self.client.post("/v1/learning/decisions", json=body)

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

    async def public_key(self) -> Dict[str, Any]:
        return await self.client.get("/v1/learning/proof-key")


class RLResource(BaseResource):
    """Reinforcement Learning training endpoints."""

    async def train_memory_manager(
        self,
        collection_id: Optional[str] = None,
        num_episodes: int = 100,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Train the Memory Manager agent using RL.

        Args:
            collection_id: Optional collection to train on
            num_episodes: Number of training episodes
            **kwargs: Additional training parameters

        Returns:
            Training results with metrics
        """
        return await self.client.post(
            "/rl/train/memory-manager",
            json={
                "collection_id": collection_id,
                "num_episodes": num_episodes,
                **kwargs,
            },
        )

    async def train_answer_agent(
        self,
        collection_id: Optional[str] = None,
        num_episodes: int = 100,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Train the Answer Agent using RL.

        Args:
            collection_id: Optional collection to train on
            num_episodes: Number of training episodes
            **kwargs: Additional training parameters

        Returns:
            Training results with metrics
        """
        return await self.client.post(
            "/rl/train/answer-agent",
            json={
                "collection_id": collection_id,
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
        return await self.client.get("/rl/metrics")

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
            "/rl/evaluate",
            json={
                "agent_type": agent_type,
                "collection_id": collection_id,
            },
        )


class ProceduralResource(BaseResource):
    """Procedural memory endpoints."""

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
        return await self.client.post(
            "/procedural",
            json={
                "name": name,
                "description": description,
                "trigger_condition": trigger_condition,
                "action_sequence": action_sequence,
                "collection_id": collection_id,
                "category": category,
                "metadata": metadata or {},
            },
        )

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

        return await self.client.get("/procedural", params=params)

    async def get(self, procedure_id: str) -> Dict[str, Any]:
        """
        Get a specific procedure.

        Args:
            procedure_id: Procedure ID

        Returns:
            Procedure data
        """
        return await self.client.get(f"/procedural/{procedure_id}")

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
        return await self.client.post(
            f"/procedural/{procedure_id}/execute",
            json={"context": context or {}},
        )

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
            data["trigger_condition"] = trigger_condition
        if action_sequence is not None:
            data["action_sequence"] = action_sequence
        if metadata is not None:
            data["metadata"] = metadata

        return await self.client.patch(f"/procedural/{procedure_id}", json=data)

    async def delete(self, procedure_id: str) -> None:
        """
        Delete a procedure.

        Args:
            procedure_id: Procedure ID
        """
        await self.client.delete(f"/procedural/{procedure_id}")


class TemporalResource(BaseResource):
    """Temporal knowledge graph endpoints."""

    async def add_fact(
        self,
        subject: str,
        predicate: str,
        object: str,
        valid_from: Optional[str] = None,
        valid_until: Optional[str] = None,
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
            "/temporal/facts",
            json={
                "subject": subject,
                "predicate": predicate,
                "object": object,
                "valid_from": valid_from,
                "valid_until": valid_until,
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
        params = {}
        if subject:
            params["subject"] = subject
        if predicate:
            params["predicate"] = predicate
        if object:
            params["object"] = object
        if at_time:
            params["at_time"] = at_time

        return await self.client.get("/temporal/facts", params=params)

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
        return await self.client.post(
            "/temporal/point-in-time",
            json={
                "timestamp": timestamp,
                "entity": entity,
            },
        )


class WorkingMemoryResource(BaseResource):
    """Working memory buffer endpoints."""

    async def add(
        self,
        role: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
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
            "/working-memory",
            json={
                "role": role,
                "content": content,
                "metadata": metadata or {},
            },
        )

    async def get_context(self) -> Dict[str, Any]:
        """
        Get current working memory context.

        Returns:
            Current context with buffer items
        """
        return await self.client.get("/working-memory/context")

    async def compress(self) -> Dict[str, Any]:
        """
        Compress working memory buffer.

        Returns:
            Compression result
        """
        return await self.client.post("/working-memory/compress")

    async def clear(self) -> Dict[str, Any]:
        """
        Clear working memory buffer.

        Returns:
            Clear result
        """
        return await self.client.delete("/working-memory")


class ConsolidationResource(BaseResource):
    """Memory consolidation endpoints."""

    async def consolidate(
        self,
        collection_id: str,
        threshold: int = 100,
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
            "/consolidation/consolidate",
            json={
                "collection_id": collection_id,
                "threshold": threshold,
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
        return await self.client.get(
            "/consolidation/stats",
            params={"collection_id": collection_id},
        )

    async def archive(
        self,
        collection_id: str,
        before_date: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Archive old memories.

        Args:
            collection_id: Collection ID
            before_date: Archive memories before this date (ISO timestamp)

        Returns:
            Archive result
        """
        return await self.client.post(
            "/consolidation/archive",
            json={
                "collection_id": collection_id,
                "before_date": before_date,
            },
        )


class MemoryToolsResource(BaseResource):
    """Self-editing memory tools endpoints."""

    async def replace(
        self,
        memory_id: str,
        new_content: str,
        reason: Optional[str] = None,
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
        return await self.client.post(
            "/memory-tools/replace",
            json={
                "memory_id": memory_id,
                "new_content": new_content,
                "reason": reason,
            },
        )

    async def insert(
        self,
        collection_id: str,
        content: str,
        position: int,
        reason: Optional[str] = None,
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
        return await self.client.post(
            "/memory-tools/insert",
            json={
                "collection_id": collection_id,
                "content": content,
                "position": position,
                "reason": reason,
            },
        )

    async def rethink(
        self,
        memory_id: str,
        query: str,
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
            "/memory-tools/rethink",
            json={
                "memory_id": memory_id,
                "query": query,
            },
        )


class WorldModelResource(BaseResource):
    """World model and planning endpoints."""

    async def imagine_retrieval(
        self,
        query: str,
        collection_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Simulate retrieval without actually retrieving.

        Args:
            query: Query to simulate
            collection_id: Optional collection

        Returns:
            Simulated retrieval result
        """
        return await self.client.post(
            "/world-model/imagine-retrieval",
            json={
                "query": query,
                "collection_id": collection_id,
            },
        )

    async def plan(
        self,
        goal: str,
        collection_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Plan memory operations to achieve goal.

        Args:
            goal: Goal to achieve
            collection_id: Optional collection

        Returns:
            Planned operations
        """
        return await self.client.post(
            "/world-model/plan",
            json={
                "goal": goal,
                "collection_id": collection_id,
            },
        )
