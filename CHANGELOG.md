# Changelog

## 2.4.1 — 2026-08-27

- Make every async and sync readiness deadline preserve the original durable
  receipt and raise top-level `IndexingTimeoutError`, including single writes,
  batches, inference jobs, and direct updates.
- Normalize memory/job/status/request/outbox/idempotency recovery metadata and
  preserve transport-only `Location`, request, retry, event, and replay headers.

## 2.4.0 — 2026-08-27

- Reconcile every exported advanced method with the canonical public OpenAPI,
  including temporal, working-memory, consolidation, memory-tool, and RL routes.
- Add a route-manifest release gate and clean-wheel installation verification.
- Treat durable-but-indexing batch results as `202`, poll them through the SDK,
  and raise `IndexingTimeoutError` with the durable receipt on client deadline.
- Preserve structured entitlement metadata in `EntitlementError`.
- Keep advanced resources async-only and document the sync-client boundary.
- Withdraw the experimental World Model from the public SDK until a trained,
  versioned production model artifact and serving contract exist.
- Publish compatibility through `GET /v1/release`; replace the broken public
  repository link with valid artifact and support links.

## 2.3.2 — 2026-08-27

- Align procedure create/list/get/update/execute/delete with the canonical
  `/v1/procedures` REST and OpenAPI contract, including idempotent `204`
  deletion.
- Add explicit synchronous/asynchronous batch readiness receipts to the async
  and synchronous clients.
- Add batch wait helpers that poll every accepted memory, propagate terminal
  failures, respect deadlines, and support asynchronous cancellation.

## 2.3.1 — 2026-08-26

- Make `wait_for_index=True` poll the authoritative memory or job readiness
  endpoint instead of returning a non-searchable receipt.
- Add `memories.wait_until_searchable(...)` to the async and synchronous
  clients, with explicit timeout and terminal-failure handling.
- Preserve valid evidence-bound search rows during a degraded or abstaining
  server response while retaining the safety metadata; malformed and explicit
  no-match envelopes still fail closed.
- Keep the synchronous and asynchronous memory create, scope, idempotency, and
  search-safety behavior aligned.
- Add `temporal.delete_fact(fact_id)` for tenant-scoped, idempotent cleanup of
  facts created through the temporal API.

The supported server/SDK release pair is published by the server OpenAPI
document in `info.x-hebbrix-sdk-compatibility`. Patch releases preserve the
public API within the same major version.

## 2.3.0

- Added the GA scoped memory, corrections, search proof, and ProofLoop surface.
