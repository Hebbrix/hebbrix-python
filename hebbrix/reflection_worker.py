"""Run one bounded native reflection job from an existing scheduler.

Required: separate HEBBRIX_REFLECTION_KEY and OPENAI_API_KEY in the process
environment. No credentials are accepted on the command line or written to disk.
Run this repeatedly from YOUR existing scheduler with a new request key only
after inspecting the prior receipt. Unknown attempts require reconciliation.
"""

import argparse
import json
import os
import sys

from hebbrix import SyncMemoryClient
from hebbrix.openai_reflection import OpenAIReflectionAdapter
from hebbrix.workflow import ReflectionUncertain, ReflectionWorker


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--program", required=True)
    parser.add_argument("--request-key", required=True)
    parser.add_argument("--base-url", default="https://api.hebbrix.com")
    parser.add_argument("--input-rate-ceiling", required=True)
    parser.add_argument("--output-rate-ceiling", required=True)
    args = parser.parse_args(argv)
    client, adapter = None, None
    try:
        client = SyncMemoryClient(
            api_key=os.environ["HEBBRIX_REFLECTION_KEY"], base_url=args.base_url
        )

        def prepare(source):
            nonlocal adapter
            # The claimed, integrity-bound input carries the immutable budget.
            # A dedicated worker needs no administrative or general read scope.
            adapter = OpenAIReflectionAdapter(
                api_key=os.environ["OPENAI_API_KEY"],
                model=source["model"],
                reservation_microusd=source["provider_budget_microusd"],
                input_usd_per_million=args.input_rate_ceiling,
                output_usd_per_million=args.output_rate_ceiling,
            )
            return adapter.prepare(source)

        receipt = ReflectionWorker(client.experiences).run_once(
            args.program,
            request_key=args.request_key,
            prepare=prepare,
            send_json_bytes=lambda body: adapter.send_json_bytes(body),
        )
        job = receipt.get("job") or {}
        print(
            json.dumps(
                {
                    "job_id": job.get("job_id"),
                    "status": job.get("status"),
                    "no_job": receipt.get("no_job"),
                    "automatic_approval": False,
                }
            )
        )
    except ReflectionUncertain as exc:
        print(
            json.dumps(
                {
                    "job_id": exc.job_id,
                    "status": "requires_reconciliation",
                    "stage": exc.stage,
                    "automatic_retry": False,
                }
            )
        )
        raise SystemExit(2) from None
    except Exception:  # noqa: BLE001 -- credential-bearing adapter errors stay private.
        print(
            json.dumps(
                {
                    "status": "configuration_or_workflow_failure",
                    "automatic_retry": False,
                }
            )
        )
        raise SystemExit(1) from None
    finally:
        for resource in (adapter, client):
            if resource is not None:
                try:
                    resource.close()
                except Exception:  # noqa: BLE001 -- never expose transport internals.
                    print('{"status":"transport_cleanup_failed"}', file=sys.stderr)


if __name__ == "__main__":
    main()
