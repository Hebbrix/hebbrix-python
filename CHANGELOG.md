# Changelog

## 2.6.0 — 2026-10-04 (stable SDK)

- Bound runtime HTTPX to `>=0.25.0,<1`, excluding incompatible 1.x prereleases.
- Add sync/async atomic setup options for explicit policy configuration and built-in success-minus-cost metrics.
- Keep advisor input/probability validation, scope and protected evidence transports unchanged.
- Backend v3 learning methods remain explicit experimental opt-ins. Stable packaging does not establish performance, calibrated confidence or execution permission.

## 2.6.0rc5 — 2026-10-03 (prerelease)

- Snapshot advisor context/candidates and reject scope overrides or mutable identities.
- Validate the complete finite logging distribution against original candidates before writing.
- Invoke the callback once; preserve caller probabilities without normalization or retries.
- Caller probabilities are not authenticated randomization; no execution authority or measured learning-performance gain is claimed.

## 2.6.0rc4 — 2026-10-02 (prerelease)

- Correct both HTTP User-Agent version strings and add a source-version parity
  check. The previously published rc3 remains unchanged; helper behavior is
  otherwise identical.

## 2.6.0rc3 — 2026-10-02 (prerelease)

- Add scoped one-call policy setup and descriptive learning-report helpers.
- Add bounded advisor callbacks that log the caller's actual chosen action and
  supplied behavior distribution; advice never executes or authorizes an action.
- These helpers require the October 2 outcome-followup backend release or a
  compatible successor. Check `/v1/release` before using the new endpoints.
- Learning performance and reliable model compliance with feedback are not
  established. This release makes no superiority or benchmark claim.

## 2.6.0rc2 — 2026-10-01 (prerelease)

- Add sync/async context enrollment, revision-checked policy configuration,
  scoped evidence cards and exact action-advice helpers.
- Preserve collection/end-user scope and JSON context. ACT remains advisory;
  callers must independently authorize external actions.
- Policy configuration/advice requires backend `e5f6g7h8i868` or a compatible
  successor. Existing protected workflow transports are unchanged.

## 2.6.0rc1 — 2026-09-09 (prerelease)

- Add sync/async native experience programs, reflection jobs, reviewed lesson
  revisions and one-use execution-permission transports.
- Bind complete model requests and tool invocations, retain uncertain delivery,
  and prevent automatic retries of potentially completed side effects.
- Add the optional bounded OpenAI reflection adapter and `hebbrix-reflect` CLI.
- Require separately scoped worker/reviewer/executor credentials and the matching
  `b5c6d7e8f959` backend. That backend is not yet deployed to public production;
  stable 2.5.0 remains the production recommendation. No autonomous actions are
  enabled by installing this package.

## 2.5.0 — 2026-09-07

- Add matching synchronous and asynchronous Evidence Loop methods: owner-managed verifiers, durable episodes, actual-execution claims, protected outcome delivery and evidence assessments.
- Preserve scope, replay, incomplete-outcome and permission receipts without converting recommendations into execution authority or falling back to caller-reported outcomes.
- Reject malformed, ambiguous or unknown evidence contracts before exposing unsupported synthesis; retain valid degraded evidence with its abstention signal.
- Protected ledger methods require the connected Evidence Loop backend. Separate verifier credentials and an independent execution/outcome check remain required; these methods do not execute actions.

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
