"""Synchronous Hebbrix client for the core memory and ProofLoop lifecycle."""

import json
import os
import time
from typing import Any, Dict, List, Optional
from urllib.parse import quote

import httpx
from hebbrix.exceptions import (
    AuthenticationError,
    EntitlementError,
    HebbrixError,
    IndexingTimeoutError,
    NotFoundError,
    RateLimitError,
    ServerError,
    ValidationError,
)
from hebbrix.resources import _canonical_search_envelope, _memory_create_payload
from hebbrix._advice import _snapshot_advisor_inputs, _validated_advisor_selection, _validate_advisor_scope, _validate_advisor_horizon


class SyncCollectionsResource:
    def __init__(self, client: "SyncMemoryClient"):
        self.client = client

    def create(
        self,
        name: str,
        description: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        return self.client.post(
            "/v1/collections",
            json={
                "name": name,
                "description": description,
                "metadata": metadata or {},
            },
        )

    def delete(self, collection_id: str) -> None:
        self.client.delete(f"/v1/collections/{collection_id}")


class SyncMemoriesResource:
    def __init__(self, client: "SyncMemoryClient"):
        self.client = client

    def create(
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
        request_kwargs: Dict[str, Any] = {
            "json": _memory_create_payload(
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
        }
        if idempotency_key:
            request_kwargs["headers"] = {"Idempotency-Key": idempotency_key}
        receipt = self.client.post("/v1/memories", **request_kwargs)
        if wait_for_index:
            receipt = self._ensure_searchable_receipt(
                receipt,
                timeout=index_timeout,
                poll_interval=index_poll_interval,
                idempotency_key=idempotency_key,
            )
        return receipt

    def create_batch(
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
        if not 1 <= len(memories) <= 100:
            raise ValueError("memories must contain between 1 and 100 items")
        if any(not str(item.get("content") or "").strip() for item in memories):
            raise ValueError("every batch memory must contain non-empty content")
        payload: Dict[str, Any] = {
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
        receipt = self.client.post("/v1/memories/batch", **kwargs)
        if wait_for_index and not (
            receipt.get("searchable") is True
            and str(receipt.get("processing_status") or "").casefold() == "completed"
        ):
            receipt = self.wait_batch_until_searchable(
                receipt,
                timeout=index_timeout,
                poll_interval=index_poll_interval,
                idempotency_key=idempotency_key,
            )
        return receipt

    def wait_batch_until_searchable(
        self,
        receipt: Dict[str, Any],
        *,
        timeout: float = 60.0,
        poll_interval: float = 0.5,
        idempotency_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Poll every item in an asynchronous batch receipt until searchable."""

        memory_ids = list(dict.fromkeys(map(str, receipt.get("memory_ids") or [])))
        if not memory_ids:
            raise ValueError("batch receipt does not contain memory_ids")
        deadline = time.monotonic() + max(0.0, timeout)
        while True:
            rows = [self.get(memory_id) for memory_id in memory_ids]
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
            time.sleep(max(0.05, poll_interval))

    def wait_until_searchable(
        self,
        memory_id: str,
        *,
        timeout: float = 60.0,
        poll_interval: float = 0.5,
    ) -> Dict[str, Any]:
        deadline = time.monotonic() + max(0.0, timeout)
        while True:
            memory = self.get(memory_id)
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
            time.sleep(max(0.05, poll_interval))

    def _ensure_searchable_receipt(
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
            try:
                job = SyncMemoryJobsResource(self.client).wait(
                    job_id,
                    timeout=timeout,
                    poll_interval=poll_interval,
                )
            except TimeoutError as exc:
                raise IndexingTimeoutError(
                    f"memory job {job_id} did not become searchable within {timeout}s; "
                    "the write is durable",
                    receipt,
                    idempotency_key=idempotency_key,
                ) from exc
            if str(job.get("status") or "").casefold() != "completed":
                raise RuntimeError(f"memory job {job_id} did not complete")
            receipt.update(job)
            receipt["searchable"] = True
            receipt["processing_status"] = "completed"
            return receipt
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
            ready = self.wait_until_searchable(
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

    def list_page(
        self,
        *,
        collection_id: Optional[str] = None,
        user_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        run_id: Optional[str] = None,
        scope: Optional[str] = None,
        cursor: Optional[str] = None,
        limit: int = 50,
        include_superseded: bool = False,
    ) -> Dict[str, Any]:
        params = {
            "collection_id": collection_id,
            "user_id": user_id,
            "agent_id": agent_id,
            "run_id": run_id,
            "scope": scope,
            "cursor": cursor,
            "limit": limit,
            "include_superseded": include_superseded,
        }
        return self.client.get(
            "/v1/memories",
            params={key: value for key, value in params.items() if value is not None},
        )

    def list(self, **kwargs) -> List[Dict[str, Any]]:
        return self.list_page(**kwargs).get("items", [])

    def get(self, memory_id: str) -> Dict[str, Any]:
        return self.client.get(f"/v1/memories/{memory_id}")

    def update(
        self,
        memory_id: str,
        *,
        content: Optional[str] = None,
        importance: Optional[float] = None,
        metadata: Optional[Dict[str, Any]] = None,
        wait_for_index: Optional[bool] = None,
        index_timeout: float = 60.0,
        index_poll_interval: float = 0.5,
    ) -> Dict[str, Any]:
        payload = {
            "content": content,
            "importance": importance,
            "metadata": metadata,
            "wait_for_index": wait_for_index,
        }
        receipt = self.client.patch(
            f"/v1/memories/{memory_id}",
            json={key: value for key, value in payload.items() if value is not None},
        )
        if wait_for_index is True:
            receipt = {**receipt, "id": receipt.get("id") or memory_id}
            receipt = self._ensure_searchable_receipt(
                receipt,
                timeout=index_timeout,
                poll_interval=index_poll_interval,
            )
        return receipt

    def delete(self, memory_id: str) -> Dict[str, Any]:
        return self.client.delete(f"/v1/memories/{memory_id}")


class SyncMemoryJobsResource:
    def __init__(self, client: "SyncMemoryClient"):
        self.client = client

    def get(self, job_id: str) -> Dict[str, Any]:
        return self.client.get(f"/v1/memory-jobs/{job_id}")

    def wait(
        self,
        job_id: str,
        *,
        timeout: float = 60.0,
        poll_interval: float = 0.5,
    ) -> Dict[str, Any]:
        deadline = time.monotonic() + max(0.0, timeout)
        while True:
            receipt = self.get(job_id)
            state = str(receipt.get("status") or "").casefold()
            if state in {"completed", "failed", "cancelled", "canceled"}:
                return receipt
            if time.monotonic() >= deadline:
                raise TimeoutError(f"memory job {job_id} did not finish in {timeout}s")
            time.sleep(max(0.05, poll_interval))


class SyncCorrectionsResource:
    def __init__(self, client: "SyncMemoryClient"):
        self.client = client

    def create(
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
        return self.client.post("/v1/corrections", **request_kwargs)

    def relevant(self, query: str, **kwargs) -> List[Dict[str, Any]]:
        params = {"query": query, **kwargs}
        return self.client.get(
            "/v1/corrections/relevant",
            params={key: value for key, value in params.items() if value is not None},
        )

    def get(self, correction_id: str) -> Dict[str, Any]:
        return self.client.get(f"/v1/corrections/{correction_id}")

    def delete(self, correction_id: str) -> Dict[str, Any]:
        return self.client.delete(f"/v1/corrections/{correction_id}")


class SyncProceduralResource:
    """Blocking procedure lifecycle mapped to the canonical REST contract."""

    def __init__(self, client: "SyncMemoryClient"):
        self.client = client

    @staticmethod
    def _unwrap(response: Dict[str, Any]) -> Dict[str, Any]:
        procedure = response.get("procedure")
        if isinstance(procedure, dict):
            return procedure
        if response.get("procedure_id") and not response.get("id"):
            return {**response, "id": response["procedure_id"]}
        return response

    def create(
        self,
        *,
        name: str,
        description: str,
        trigger_condition: str,
        action_sequence: List[str],
        collection_id: Optional[str] = None,
        category: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        response = self.client.post(
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
        return self._unwrap(response)

    def list(
        self,
        *,
        collection_id: Optional[str] = None,
        category: Optional[str] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        response = self.client.get(
            "/v1/procedures",
            params={
                key: value
                for key, value in {
                    "collection_id": collection_id,
                    "category": category,
                    "skip": skip,
                    "limit": limit,
                }.items()
                if value is not None
            },
        )
        return (
            response if isinstance(response, list) else response.get("procedures", [])
        )

    def get(self, procedure_id: str) -> Dict[str, Any]:
        return self._unwrap(self.client.get(f"/v1/procedures/{procedure_id}"))

    def update(
        self,
        procedure_id: str,
        *,
        name: Optional[str] = None,
        description: Optional[str] = None,
        trigger_condition: Optional[str] = None,
        action_sequence: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {}
        if name is not None:
            payload["name"] = name
        if description is not None:
            payload["description"] = description
        if trigger_condition is not None:
            payload["condition"] = {"expression": trigger_condition}
        if action_sequence is not None:
            payload["action"] = {"steps": action_sequence}
        if metadata is not None:
            payload["parameters"] = metadata
        return self._unwrap(
            self.client.patch(f"/v1/procedures/{procedure_id}", json=payload)
        )

    def execute(
        self,
        procedure_id: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        response = self.client.post(
            f"/v1/procedures/{procedure_id}/execute",
            json={"input_state": context or {}},
        )
        result = response.get("execution_result")
        return result if isinstance(result, dict) else response

    def delete(self, procedure_id: str) -> None:
        self.client.delete(f"/v1/procedures/{procedure_id}")


class SyncSearchResource:
    def __init__(self, client: "SyncMemoryClient"):
        self.client = client

    def search_with_proof(
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
        view: Optional[str] = None,
    ) -> Dict[str, Any]:
        from ._advice import _validate_advice_view
        _validate_advice_view(view)
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
            "view": view,
        }
        if fast is not None:
            payload["fast"] = fast
        if threshold is not None:
            payload["threshold"] = threshold
        response = self.client.post(
            "/v1/search",
            json={key: value for key, value in payload.items() if value is not None},
        )
        return _canonical_search_envelope(response)

    def search(self, *args, **kwargs) -> List[Dict[str, Any]]:
        return self.search_with_proof(*args, **kwargs).get("results", [])

    def reason(
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
        response = self.client.post(
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


class SyncProofLoopResource:
    def __init__(self, client: "SyncMemoryClient"):
        self.client = client

    def decide(
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
        return self.client.post("/v1/learning/decisions", json=body)

    def decide_batch(self, items: List[Dict[str, Any]], *,
                     view: str = "compact") -> Dict[str, Any]:
        """1-50 idempotent requests; partial acceptance, never execution authority."""
        from ._advice import _batch_payload
        return self.client.post("/v1/learning/decisions/batch",
            json=_batch_payload(items, view))

    def record_outcomes_batch(self, items: List[Dict[str, Any]], *,
                              view: str = "compact") -> Dict[str, Any]:
        """Independently committed outcomes; inspect each accepted/rejected result."""
        from ._advice import _batch_payload
        return self.client.post("/v1/learning/outcomes/batch",
            json=_batch_payload(items, view, outcomes=True))

    def register_verifier(
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
        return self.client.post(
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

    def revoke_verifier(self, verifier_id: str) -> Dict[str, Any]:
        """Revoke one source without deleting historical evidence."""
        return self.client.post(
            f"/v1/learning/verifiers/{quote(verifier_id, safe='')}/revoke", json={}
        )

    def create_episode(
        self,
        *,
        policy_key: str,
        verifier_id: str,
        idempotency_key: str,
        collection_id: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create a scoped durable episode; never grants execution permission."""
        return self.client.post(
            "/v1/learning/episodes",
            json={
                "policy_key": policy_key,
                "verifier_id": verifier_id,
                "idempotency_key": idempotency_key,
                "collection_id": collection_id,
                "user_id": user_id,
            },
        )

    def get_episode(self, episode_id: str, *, offset: int = 0) -> Dict[str, Any]:
        return self.client.get(
            f"/v1/learning/episodes/{quote(episode_id, safe='')}",
            params={"offset": offset},
        )

    def close_episode(self, episode_id: str, *, status: str) -> Dict[str, Any]:
        return self.client.post(
            f"/v1/learning/episodes/{quote(episode_id, safe='')}/close",
            json={"status": status},
        )

    def record_execution(
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
        return self.client.post(
            f"/v1/learning/decisions/{quote(decision_id, safe='')}/executions",
            json=body,
        )

    def assessment(
        self, decision_id: str, *, evidence_offset: int = 0
    ) -> Dict[str, Any]:
        return self.client.get(
            f"/v1/learning/decisions/{quote(decision_id, safe='')}/assessment",
            params={"evidence_offset": evidence_offset},
        )

    def assess_experience(
        self, *, candidate: Dict[str, Any], context: Dict[str, Any],
        collection_id: Optional[str] = None, user_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Revalidate an experience hypothesis. Never grants execution permission."""
        return self.client.post(
            "/v1/learning/experiences/assess",
            json={"candidate": candidate, "context": context,
                  "collection_id": collection_id, "user_id": user_id},
        )

    def experience_context(
        self, *, memory_collection_id: str, policy_key: str,
        references: List[Dict[str, Any]], context: Dict[str, Any],
        evidence_collection_id: Optional[str] = None,
        user_id: Optional[str] = None, agent_id: Optional[str] = None,
        run_id: Optional[str] = None, max_context_bytes: int = 16000,
    ) -> Dict[str, Any]:
        """Revalidate stored hypotheses. The response is not execution permission."""
        return self.client.post(
            "/v1/learning/experiences/context",
            json={
                "memory_collection_id": memory_collection_id,
                "evidence_collection_id": evidence_collection_id,
                "user_id": user_id, "agent_id": agent_id, "run_id": run_id,
                "policy_key": policy_key, "references": references,
                "context": context, "max_context_bytes": max_context_bytes,
            },
        )

    def verifier_evidence(self, verifier_id: str, decision_id: str) -> Dict[str, Any]:
        """Call with the dedicated verifier client, never the actor's credential."""
        return self.client.get(
            f"/v1/learning/verifiers/{quote(verifier_id, safe='')}/decisions/{quote(decision_id, safe='')}"
        )

    def deliver_verified_outcomes(
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
        return self.client.post(
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

    def get_decision(self, decision_id: str) -> Dict[str, Any]:
        return self.client.get(f"/v1/learning/decisions/{decision_id}")

    def register_context_schema(
        self,
        policy_key: str,
        *,
        context_schema: Dict[str, Any],
        collection_id: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Enroll before any decisions; changing learning semantics needs a new policy."""
        return self.client.request(
            "PUT",
            f"/v1/learning/policies/{quote(policy_key, safe='')}/context-schema",
            json={
                "context_schema": context_schema,
                "collection_id": collection_id,
                "user_id": user_id,
            },
        )

    def context_schema(
        self,
        policy_key: str,
        *,
        collection_id: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        return self.client.get(
            f"/v1/learning/policies/{quote(policy_key, safe='')}/context-schema",
            params={
                k: v
                for k, v in {"collection_id": collection_id, "user_id": user_id}.items()
                if v is not None
            },
        )

    def setup_policy(self, policy_key: str, *, context_schema: Dict[str, Any],
                           actions: Dict[str, Any], collection_id: Optional[str] = None,
                           user_id: Optional[str] = None,
                           configuration: Optional[Dict[str, Any]] = None,
                           value_objective: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """One atomic setup call. Risk/target/description are supplied by the owner.
        Only explicitly low-risk exploration_allowed actions learn by default.
        This neither permits execution nor changes an existing policy.
        """
        return self.client.post(f"/v1/learning/policies/{quote(policy_key, safe='')}/setup",
            json=dict(collection_id=collection_id, user_id=user_id,
                context_schema=context_schema,
                configuration={**(configuration or {}), "actions": actions},
                **({"value_objective": value_objective} if value_objective is not None else {})))

    def learning_report(self, policy_key: str, *, days: int = 7,
                              collection_id: Optional[str] = None,
                              user_id: Optional[str] = None) -> Dict[str, Any]:
        """Bounded descriptive report, not a causal uplift or execution guarantee."""
        return self.client.get(f"/v1/learning/policies/{quote(policy_key, safe='')}/report",
            params={k: v for k, v in dict(days=days, collection_id=collection_id,
                user_id=user_id).items() if v is not None})

    def decide_with_advice(self, *, policy_key: str, candidates: List[Dict[str, Any]],
                                 context: Dict[str, Any], advisor,
                                 collection_id: Optional[str] = None,
                                 user_id: Optional[str] = None,
                                 idempotency_key: Optional[str] = None,
                                 remaining_decisions: Optional[int] = None,
                                 max_pilot_decisions: Optional[int] = None,
                                 view: Optional[str] = None) -> Dict[str, Any]:
        """Read evidence, call your advisor once, then log its explicit choice.
        advisor must return chosen_action_key, action_probability and the complete
        behavior_probabilities. No model confidence is invented as a propensity.
        Inputs are detached before reading evidence; callback mutations cannot
        change the logged scope/candidates/context. Malformed distributions fail
        before logging, without retries or normalization. Caller probabilities
        remain caller-reported, not authenticated randomization. No tool execution
        or outcome is recorded by this helper.
        """
        _validate_advisor_scope(policy_key, collection_id, user_id, idempotency_key)
        _validate_advisor_horizon(remaining_decisions, max_pilot_decisions)
        from ._advice import _validate_advice_view
        _validate_advice_view(view)
        candidates, context, keys = _snapshot_advisor_inputs(candidates, context)
        if not callable(advisor):
            raise ValueError("advisor must be callable")
        card = self.policy_advice(policy_key, context=context,
            collection_id=collection_id, user_id=user_id,
            remaining_decisions=remaining_decisions, max_pilot_decisions=max_pilot_decisions,
            **({"view": view} if view is not None else {}))
        selection = _validated_advisor_selection(advisor(card), keys)
        return self.decide(policy_key=policy_key, candidates=candidates, context=context,
            collection_id=collection_id, user_id=user_id, idempotency_key=idempotency_key,
            mode="observe", **selection)

    def configure_policy(self, policy_key: str, *, configuration: Dict[str, Any],
                               expected_revision: int = 0, collection_id: Optional[str] = None,
                               user_id: Optional[str] = None) -> Dict[str, Any]:
        """Explicit risk/strategy opt-in, revision-checked; not execution permission."""
        return self.client.request("PUT",
            f"/v1/learning/policies/{quote(policy_key, safe='')}/configuration",
            json=dict(configuration=configuration, expected_revision=expected_revision,
                      collection_id=collection_id, user_id=user_id))

    def policy_configuration(self, policy_key: str, *, collection_id: Optional[str] = None,
                                   user_id: Optional[str] = None) -> Dict[str, Any]:
        return self.client.get(f"/v1/learning/policies/{quote(policy_key, safe='')}/configuration",
            params={k: v for k, v in dict(collection_id=collection_id, user_id=user_id).items() if v is not None})

    def policy_advice(self, policy_key: str, *, context: Optional[Dict[str, Any]] = None,
                      collection_id: Optional[str] = None, user_id: Optional[str] = None,
                      remaining_decisions: Optional[int] = None,
                      max_pilot_decisions: Optional[int] = None,
                      view: Optional[str] = None) -> Dict[str, Any]:
        """Read caller-reported evidence and a candidate, never an execution permit."""
        from ._advice import _validate_advice_view
        _validate_advice_view(view)
        return self.client.get(f"/v1/learning/policies/{quote(policy_key, safe='')}/advice",
            params={k: v for k, v in dict(context=json.dumps(context or {}),
                collection_id=collection_id, user_id=user_id,
                remaining_decisions=remaining_decisions, max_pilot_decisions=max_pilot_decisions,
                view=view).items() if v is not None})

    def action_advice(self, query: str, *, policy_key: str, action_key: str,
                     context: Optional[Dict[str, Any]] = None, collection_id: Optional[str] = None,
                           user_id: Optional[str] = None) -> Dict[str, Any]:
        """Read ASK/REVIEW/ACT advice for an exact configured action. ACT is not permission."""
        return self.client.get("/v1/confidence", params={k: v for k, v in
            dict(query=query, policy_key=policy_key, action_key=action_key,
                 context=json.dumps(context or {}), collection_id=collection_id,
                 end_user_id=user_id).items() if v is not None})

    def define_metric(
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
        return self.client.post(
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

    def list_metrics(
        self,
        *,
        policy_key: Optional[str] = None,
        collection_id: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        params = {
            key: value
            for key, value in {
                "policy_key": policy_key,
                "collection_id": collection_id,
                "user_id": user_id,
            }.items()
            if value is not None
        }
        return self.client.get("/v1/learning/metrics", params=params)

    def policy_insights(
        self,
        policy_key: str,
        *,
        collection_id: Optional[str] = None,
        user_id: Optional[str] = None,
        action_keys: Optional[List[str]] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        params = {
            key: value
            for key, value in {
                "collection_id": collection_id,
                "user_id": user_id,
                "action_key": action_keys,
                "context": json.dumps(context) if context is not None else None,
            }.items()
            if value is not None
        }
        return self.client.get(
            f"/v1/learning/policies/{policy_key}/insights", params=params
        )

    def evaluate_policy(
        self,
        policy_key: str,
        *,
        collection_id: Optional[str] = None,
        user_id: Optional[str] = None,
        limit: int = 5000,
    ) -> Dict[str, Any]:
        return self.client.post(
            f"/v1/learning/policies/{policy_key}/evaluate",
            json={
                "collection_id": collection_id,
                "user_id": user_id,
                "limit": limit,
            },
        )

    def record_outcome(
        self,
        decision_id: str,
        *,
        observations: Optional[List[Dict[str, Any]]] = None,
        reward: Optional[float] = None,
        success: Optional[bool] = None,
        idempotency_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        return self.client.post(
            f"/v1/learning/decisions/{decision_id}/outcomes",
            json={
                "observations": observations or [],
                "reward": reward,
                "success": success,
                "idempotency_key": idempotency_key,
            },
        )

    def proof(self, decision_id: str) -> Dict[str, Any]:
        return self.client.get(f"/v1/learning/decisions/{decision_id}/proof")

    def confirm_capture(self, decision_id: str, *, observation_id: str,
                        idempotency_key: str, success: bool, confirmed: bool,
                        collection_id: Optional[str] = None,
                        user_id: Optional[str] = None,
                        source_system: Optional[str] = None,
                        source_event_id: Optional[str] = None,
                        evidence_digest: Optional[str] = None) -> Dict[str, Any]:
        """Caller confirmation, never automatic promotion or independent verification."""
        from ._advice import _confirmation_payload
        body = _confirmation_payload(observation_id, idempotency_key, success,
            confirmed, collection_id, user_id, source_system, source_event_id,
            evidence_digest)
        return self.client.post(
            f"/v1/learning/decisions/{quote(decision_id, safe='')}/confirm-capture",
            json=body)

    def public_key(self, key_id: Optional[str] = None) -> Dict[str, Any]:
        params = {"key_id": key_id} if key_id else None
        return self.client.get("/v1/learning/proof-key", params=params)


class SyncMemoryClient:
    """Blocking client for memory creation, scoped search, and ProofLoop."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: str = "https://api.hebbrix.com",
        timeout: float = 120.0,
        source: Optional[str] = None,
    ):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.source = source or os.getenv("HEBBRIX_SOURCE")
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "hebbrix-python/2.6.2",
        }
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        if self.source:
            headers["X-Hebbrix-Source"] = self.source
        self._client = httpx.Client(
            base_url=self.base_url,
            timeout=timeout,
            headers=headers,
        )
        self.collections = SyncCollectionsResource(self)
        self.memories = SyncMemoriesResource(self)
        self.memory_jobs = SyncMemoryJobsResource(self)
        self.corrections = SyncCorrectionsResource(self)
        self.procedural = SyncProceduralResource(self)
        self.search_resource = SyncSearchResource(self)
        self.proofloop = SyncProofLoopResource(self)
        from hebbrix.workflow import ExperienceWorkflow

        self.experiences = ExperienceWorkflow(self)

    @staticmethod
    def _handle_error(response: httpx.Response) -> None:
        try:
            error_data = response.json()
        except Exception:
            error_data = {}
        envelope = error_data.get("error") or error_data.get("detail") or {}
        if not isinstance(envelope, dict):
            envelope = {"message": str(envelope)}
        nested = envelope.get("message")
        detail = nested if isinstance(nested, dict) else envelope
        details = detail if isinstance(detail, dict) else {}
        message = (
            (details.get("message"))
            or (nested if isinstance(nested, str) else None)
            or response.text
        )
        code = str(details.get("code") or envelope.get("code") or "") or None
        request_id = (
            details.get("request_id")
            or envelope.get("request_id")
            or response.headers.get("X-Request-ID")
        )
        if response.status_code == 401:
            raise AuthenticationError(
                message, code=code, request_id=request_id, details=details
            )
        if response.status_code == 404:
            raise NotFoundError(
                message, code=code, request_id=request_id, details=details
            )
        if response.status_code == 422:
            raise ValidationError(
                message,
                errors=detail if isinstance(detail, list) else [],
                code=code,
                request_id=request_id,
                details=details,
            )
        if response.status_code == 429:
            raise RateLimitError(
                message, code=code, request_id=request_id, details=details
            )
        if response.status_code >= 500:
            raise ServerError(
                message, code=code, request_id=request_id, details=details
            )
        if response.status_code in {402, 403} and (
            "ENTITLEMENT" in str(code or "")
            or details.get("error")
            in {"feature_not_available", "tier_upgrade_required"}
        ):
            raise EntitlementError(
                message,
                status_code=response.status_code,
                code=code,
                request_id=request_id,
                details=details,
            )
        raise HebbrixError(
            message,
            status_code=response.status_code,
            code=code,
            request_id=request_id,
            details=details,
        )

    def request(self, method: str, path: str, **kwargs) -> Dict[str, Any]:
        response = self._client.request(method, path, **kwargs)
        if response.status_code >= 400:
            self._handle_error(response)
        payload = response.json() if response.text else {}
        if isinstance(payload, dict):
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

    def get(self, path: str, **kwargs) -> Dict[str, Any]:
        return self.request("GET", path, **kwargs)

    def post(self, path: str, **kwargs) -> Dict[str, Any]:
        return self.request("POST", path, **kwargs)

    def patch(self, path: str, **kwargs) -> Dict[str, Any]:
        return self.request("PATCH", path, **kwargs)

    def delete(self, path: str, **kwargs) -> Dict[str, Any]:
        return self.request("DELETE", path, **kwargs)

    def search(self, *args, **kwargs) -> List[Dict[str, Any]]:
        return self.search_resource.search(*args, **kwargs)

    def search_with_proof(self, *args, **kwargs) -> Dict[str, Any]:
        return self.search_resource.search_with_proof(*args, **kwargs)

    def reason(self, *args, **kwargs) -> Dict[str, Any]:
        return self.search_resource.reason(*args, **kwargs)

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "SyncMemoryClient":
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()
