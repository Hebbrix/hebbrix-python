"""Opt-in live test for the complete high-level, user-scoped SDK lifecycle.

Run with HEBBRIX_INTEGRATION_API_KEY set. The test owns and deletes a uniquely
named collection and never depends on pre-existing tenant data.
"""

import base64
import json
import os
import uuid
from typing import Dict

import pytest
from hebbrix import MemoryClient

API_KEY = os.getenv("HEBBRIX_INTEGRATION_API_KEY")
BASE_URL = os.getenv("HEBBRIX_INTEGRATION_BASE_URL", "https://api.hebbrix.com")

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        not API_KEY,
        reason="set HEBBRIX_INTEGRATION_API_KEY to run the disposable live test",
    ),
]


def _dsse_pae(payload_type: str, payload: bytes) -> bytes:
    encoded_type = payload_type.encode("utf-8")
    return b"DSSEv1 %d %s %d %s" % (
        len(encoded_type),
        encoded_type,
        len(payload),
        payload,
    )


def _verify_attestation(proof: Dict, public_key_document: Dict) -> None:
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec

    envelope = proof["attestation"]["envelope"]
    signature = envelope["signatures"][0]
    payload = base64.b64decode(envelope["payload"], validate=True)
    public_key = serialization.load_pem_public_key(
        public_key_document["public_key_pem"].encode("ascii")
    )
    public_key.verify(
        base64.b64decode(signature["sig"], validate=True),
        _dsse_pae(envelope["payloadType"], payload),
        ec.ECDSA(hashes.SHA256()),
    )
    statement = json.loads(payload)
    bundle_digest = proof["bundle_digest"]
    expected_digest = (
        bundle_digest[len("sha256:") :]
        if bundle_digest.startswith("sha256:")
        else bundle_digest
    )
    assert statement["subject"][0]["digest"]["sha256"] == expected_digest


async def test_complete_user_scoped_proofloop_lifecycle() -> None:
    run_id = uuid.uuid4().hex
    owner_user_id = f"sdk-owner-{run_id}"
    other_user_id = f"sdk-other-{run_id}"
    content = f"SDK proof marker {run_id}: concise responses are preferred."

    async with MemoryClient(api_key=API_KEY, base_url=BASE_URL) as client:
        collection = await client.collections.create(
            name=f"sdk-proofloop-{run_id}",
            description="Disposable Python SDK integration test",
        )
        collection_id = collection.get("id") or collection["collection_id"]
        try:
            created = await client.memories.create(
                collection_id=collection_id,
                content=content,
                user_id=owner_user_id,
                source_type="sdk_integration_test",
                source_reference=f"run:{run_id}",
                metadata={"disposable": True, "run_id": run_id},
                infer=False,
                wait_for_index=True,
            )
            assert created.get("results")

            scoped_search = await client.search_with_proof(
                content,
                collection_id=collection_id,
                user_id=owner_user_id,
            )
            assert scoped_search["results"]
            assert scoped_search["proof_context"]["token"]

            cross_user_search = await client.search_with_proof(
                content,
                collection_id=collection_id,
                user_id=other_user_id,
            )
            assert cross_user_search["results"] == []

            decision = await client.proofloop.decide(
                policy_key="sdk.user_scope.integration",
                candidates=[
                    {"action_key": "use_concise"},
                    {"action_key": "ask_user"},
                ],
                chosen_action_key="use_concise",
                baseline_action_key="ask_user",
                action_probability=1.0,
                mode="observe",
                collection_id=collection_id,
                user_id=owner_user_id,
                idempotency_key=f"decision-{run_id}",
                proof_context=scoped_search["proof_context"],
            )
            await client.proofloop.record_outcome(
                decision["decision_id"],
                success=True,
                idempotency_key=f"outcome-{run_id}",
            )
            proof = await client.proofloop.proof(decision["decision_id"])
            assert proof["digest_consistent"] is True
            assert proof["bundle_digest"].startswith("sha256:")

            if proof["attested"]:
                signature = proof["attestation"]["envelope"]["signatures"][0]
                key = await client.proofloop.public_key(signature["keyid"])
                _verify_attestation(proof, key)
            else:
                # Local stacks intentionally run without KMS. Production
                # acceptance sets HEBBRIX_REQUIRE_ATTESTATION=1 below.
                assert not os.getenv("HEBBRIX_REQUIRE_ATTESTATION")
        finally:
            await client.collections.delete(collection_id)
