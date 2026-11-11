# Changelog

## 2.10.0 — 2026-11-12 (applicable rules, consistent abstention flags)

- An `unverified` search response whose rows include `evidence_role: "applicable_rule"` (server 1.4.27) returns reason `applicable_rule` and action `use_as_context`, those rules first in `decision.context`: policy that speaks to the asked case but that the API has not verified decides it. Let your model apply it, or call `reason`. A rule is never an authorization; `authorization_not_verifiable` still comes first.
- `history=True` no longer overrides an explicit abstention flag on an `answerable` response: a response marked `answerable` that also sets `no_match`, `abstain_recommended` or `decision_abstained` contradicts itself and is declined in every mode, with that flag as the reason. History mode still answers a `superseded` response from its earlier versions (its flags concern the present), never one with `no_match`.

## 2.9.0 — 2026-11-11 (high-stakes readiness, history and suggestions)

- `should_answer(response, require_ready=True)` (also on `usable_memories` and `answer_context`): for high-stakes flows, holds the answer with action `retry` and reason `index_not_ready` until `indexing.status` is `ready` and `indexing.answer_risk` is `none`. A response that does not report its indexing is not ready.
- Behaviour change: `history=True` now applies only when the server answered or marked the response `superseded`; it no longer overrides `unverified`, `no_relevant_memory` or `indexing`.
- A Reason result for a suggestion or plan (`grounding.answerability: "context_only"`) returns action `use_as_context` with its memories in `context`; `answer_context` lists them as context that is neither an established fact nor permission to act.
- `answer_context` says when recent writes could not be reflected in the profile (`projection.status: "failed"`, server 1.4.25).

## 2.8.0 — 2026-11-11 (answer decisions and answer context)

- New `hebbrix.should_answer(response)`: decides in code whether a `search_with_proof()` or `reason()` response may be answered from, returning an `AnswerDecision` with `action` (`answer`, `say_unknown`, `abstain`, `verify_authorization`, `ask_user`, `retry` or `say_no_longer_current`), `reason`, the usable `memories` and the `context` rows never to answer from. `history=True` counts superseded and historical versions for questions about the past.
- New `hebbrix.answer_context(response, decision)`: renders the end user's standing profile (facts with category, confidence and date, topics to avoid, scope, and whether it is still being projected or unavailable) beside the rows the decision allows, each with its date, memory type, subject and support.
- New `hebbrix.usable_memories(response)` and the response types `AnswerStatus`, `RevisionStatus`, `MemoryRow`, `MemoryStatus` and `ScopeIndexing`.
- `MemoryClient.search_with_proof()` accepts `include_profile` and `include_superseded`, as the synchronous client and `search()` already did.
- Docs: `memories.create()` stores verbatim unless `infer=True`, while `POST /v1/memories` extracts by default; examples pass `infer` and `wait_for_index` explicitly.

## 2.7.0 — 2026-10-19 (compact responses, entity scope, chat answers)

- Behaviour change: `search()` and `search_with_proof()` now request `view="compact"` by default (rows keep content, identity, score, rank, timestamps, `low_confidence` and entity scope; the safety envelope and proof context are unchanged; ranking diagnostics need `debug=True`). Pass `view="full"` for the previous per-row metadata. `search()` returns rows only and no longer requests the unused ProofLoop token unless `include_proof_context=True`.
- `reason()` now requests `view="compact"` by default: the answer, abstention fields (`decision_abstained`, `abstain_reason`), cited sources and safety envelope are kept and the internal decision diagnostics are omitted. Pass `view="full"` or `debug=True` for the full response.
- Add `prefer_entity_match` (both search methods) and `include_profile` (`search_with_proof`), sent only when enabled; type `query_entities`, `profile` and `view` on the search envelope.
- `MemoryChat.send()` and `send_with_context()` accept optional `answer_style` (`"natural"`, the server default, or `"quote"`) and `no_information_reply`; they are sent only when set.
- Requires the server release of 2026-10-19 for the `/search/reason` compact view; the other options are accepted by current servers.

## 2.6.3 — 2026-10-14 (candidate memory_ids)

- Candidates may carry optional `memory_ids` (at most 50 ids of 1-255 characters) naming the exact memories that action applies; when the candidate becomes the decision's action, its outcome is credited to those memories.
- The advisor input snapshot (`decide_with_advice`) admits and validates `memory_ids` before any evidence read, callback or write; `proofloop.decide` documents the candidate shape.
- Requires the server release that credits outcomes only to memories bound to the action taken; a `proof_context` attests what was retrieved and no longer earns per-memory outcome credit by itself.

## 2.6.2 — 2026-10-06 (compact advice, batches and confirmation)

- Correct canonical documentation metadata and simplify the stable three-call guide.
- Add optional compact search/advice, bounded independently committed decision/outcome batches, and explicit caller-confirmation transports.
- Add bounded chat-learning wait options while preserving the original job receipt.
- Keep historical confidence scope aliases, ACT-as-advice and protected outcome boundaries intact.
- Requires a matching server release; no benchmark superiority, latency SLA or automatic execution is implied.

## 2.6.1 — 2026-10-04 (advisory horizon helpers)

- Carry optional remaining_decisions and max_pilot_decisions through evidence reads and the once-only advisor callback.
- Keep actual caller distribution validation, owner scope and observe-mode logging unchanged.
- New backend v3 controls remain explicit experimental opt-ins; these helpers do not execute actions or establish performance, calibration or superiority.

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
