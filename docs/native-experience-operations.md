# Native experience workflow: operator and adapter contract

Local release candidate, September 9, 2026. These additions are not yet the live
production API. Use the deployed release manifest, not this document, to determine
which backend and published SDK versions are available.

## Authority and enrollment

The existing protected Evidence Loop remains the only outcome ledger. An owner
session enrolls a program for an exact evidence collection, lesson collection,
end-user/agent/run scope and versioned policy key. Program configuration is
immutable: explicit provider model, typed applicability keys, source start time,
attempt limit, total budget, per-attempt reservation and lease duration.

Use separate credentials, each with exactly its designated scope:

| Role | Authority |
| --- | --- |
| Owner session | Enroll/stop programs, designate credentials, define and activate permission policies |
| `learning:reflect` | Claim and deliver the designated program's reflection jobs; cannot review or authorize actions |
| `learning:review` | Review or revise the designated program's hypotheses; cannot change the source outcomes or execution policy |
| `learning:execute` | Request one-use admission for the exact owner-approved tool, target and action; cannot promote policy |
| Protected verifier | Existing separately scoped evidence-delivery authority; not a reflection/review credential |

Separate credentials do not make the same operator an independent evaluator.
Model text never grants any of these roles. There is no automatic enrollment,
provider spend, policy activation or production action on SDK import.

## Reflection: a durable job, not a request retry loop

`client.experiences` exposes the native program, job, lesson, review and permission
resources in Python (sync/async) and TypeScript (typed transport). Job discovery
considers mature, complete protected decisions, current verifier authority and
exact source revisions. Missing or immature observations are not negative rewards.

Claim commits a bounded reservation before returning work. The SDK seals the
whole model request, including the exact integrity-bound source in an untrusted
input field. Dispatch is a separate one-use acknowledgment; the provider is
called only after it succeeds. No provider call happens inside a database
transaction. Complete records the original response digest, bounded parsed
hypotheses and reported cost. Exact completion replay does not charge twice.

One provider-neutral `ReflectionWorker.run_once` call handles at most one job;
`AsyncReflectionWorker` has the corresponding async interface. The optional
`OpenAIReflectionAdapter` makes one bounded Responses call, with no tools,
redirects, proxy inheritance or automatic retries. Owner-enrolled model identity,
maximum output and explicit input/output price ceilings bind its reservation.
The accounting is a conservative token-price estimate, not a provider invoice.

The candidate Python wheel installs `hebbrix-reflect`:

```sh
hebbrix-reflect --program PROGRAM_ID --request-key DURABLE_ATTEMPT_ID \
  --input-rate-ceiling INPUT_USD_PER_MILLION \
  --output-rate-ceiling OUTPUT_USD_PER_MILLION
```

The uppercase arguments are placeholders. Supply `HEBBRIX_REFLECTION_KEY` and
`OPENAI_API_KEY` through the existing secret manager/process environment, never
command-line arguments. This command can run in an existing scheduler; no new
infrastructure is required. It prints IDs and statuses, not source payloads or
provider credentials. Use the same durable request key to inspect/reconcile the
same attempt; do not generate a fresh key merely because an HTTP request timed out.

An undelivered acknowledgment, provider timeout, malformed output or uncertain
completion requires reconciliation. The server retains a dispatched/unknown job
and its reservation rather than silently buying another call. A known exact
completion payload may be delivered again without repeating the provider. The
CLI exits 2 for uncertainty and 1 for configuration/workflow failure. An existing
unknown job returned on replay is status information, not permission to retry;
schedulers must inspect the JSON status as well as the process exit status.
There is no general owner "release unknown spend" button: do not edit its database
row to pretend an ambiguous provider request never happened.

## Review, revision and search publication

Candidates contain advice, proposed explanation, limitations and required future
verification. They start without approval. Review queue responses include the
bound source input and current review head. Candidate/source/review artifacts use
canonical JSON envelopes; `decode_artifact` validates their content and digest.
They remain data, never executable instructions.

The designated reviewer or owner appends `eligible`, `blocked` or `retracted` with
the expected candidate digest and prior sequence/digest. Concurrent stale reviews
conflict rather than overwrite each other. An eligible review publishes a native
memory through the transactional indexing outbox and existing quota guard. The
receipt does not claim indexing finished: inspect/poll its actual indexing state.

To improve a blocked hypothesis, use `experiences.revise` with a stable request
key, expected parent review head, candidate digest, rationale and new hypothesis.
This creates a child; it does not rewrite the original model output or source.
Its birth record explicitly identifies a curator-authored revision and starts
blocked. It still needs normal review before use. Wording may change, but source,
policy, action and applicability may not. New evidence requires a fresh job.

Always obtain current context before use. Native governance cannot be bypassed by
removing/copying metadata from a managed lesson. Corrections, deleted/edited
memories, withdrawn reviews, revoked verifiers and changed applicability cause
rejection on the next assessment or admission. A search hit or old cached positive
assessment is not a reusable grant. Review admission means eligible for evaluation,
not verified truth or proven causal value.

## Permissioned execution and rollback

An owner defines an immutable rule: designated actor, tool key, exact target
descriptor digest, allowed action keys, argument-byte cap, dispatch-count cap,
short permit lifetime and the constrained adapter's capability contract. Defining
a rule does not activate it. Promotion is an explicit owner compare-and-swap
activation record. Activation with `policy_id: null` disables new admission;
reactivating an older policy is a new epoch, not deletion of intervening history.

Permit issuance binds a pending actual decision, current lesson/review/source,
current activation epoch and exact invocation. Issuance consumes conservative
capacity but does **not** authorize execution. Only the separate dispatch endpoint
can return `authorization_granted: true`, once. Concurrent correction/revocation,
review and memory writers serialize with admission; an earlier committed change
invalidates the grant. Expiry is checked again after lock acquisition.

Python `GuardedExecution.dispatch` or `dispatch_async` passes exactly the admitted
JSON bytes to a caller-owned constrained adapter. Cancellation, lost responses,
concurrent calls and tool errors consume that attempt; they do not retry a remote
side effect. The adapter must bind the descriptor to the actual target and expose
only the approved capability. This SDK is not a sandbox, shell policy, network
firewall, or attestation that the remote action actually ran. Revocation cannot
undo an already-admitted/in-flight action. Record actual execution and deliver
the independently measured outcome through the protected ledger.

## Prerelease compatibility

Python `2.6.0rc1` and TypeScript `2.5.0-rc.1` expose the candidate native
experience contract. Those operations require backend schema `b5c6d7e8f959`;
the public production API has not enabled them yet. The current stable clients
remain Python `2.5.0` and TypeScript `2.4.0`. Check `GET /v1/release` before using
the extension. Do not silently substitute caller-reported outcomes, approval or
execution if the required backend operation is unavailable.

## What these controls do not establish

They do not establish outcome-specific transfer, independent business truth,
customer ROI, or causal attribution over a long chain of actions. Frozen metric
contracts, maturity, censoring and corrections support delayed measurement, but
long-horizon causal credit and learned policy promotion require further evidence.
No autonomous production action or automatic reward-based promotion is enabled.
