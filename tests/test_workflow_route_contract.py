"""Standalone release guard for every native sync and async transport method."""
import inspect
import json
import re
from pathlib import Path

import pytest
from hebbrix.workflow import AsyncExperienceWorkflow, ExperienceWorkflow

CONTRACT = json.loads((Path(__file__).parents[1] / "contracts/openapi-routes.json").read_text())


def routes():
    return [(method, "^" + re.sub(r"\{[^}]+\}", "[^/]+", path) + "$")
            for path, methods in CONTRACT["paths"].items() for method in methods]


@pytest.mark.asyncio
@pytest.mark.parametrize("resource", [ExperienceWorkflow, AsyncExperienceWorkflow])
async def test_all_native_methods_resolve_to_exported_operations(resource):
    observed = []

    class Transport:
        def __getattr__(self, method):
            def send(path, **kwargs):
                observed.append((method, path))
                if resource is AsyncExperienceWorkflow:
                    async def completed():
                        return {}
                    return completed()
                return {}
            return send

    client = resource(Transport())
    methods = [name for name, value in vars(resource).items()
               if not name.startswith("_") and callable(value)]
    for name in methods:
        call = getattr(client, name)
        params = {name: "contract-id" for name, p in inspect.signature(call).parameters.items()
                  if p.default is inspect.Parameter.empty and p.kind not in
                  (inspect.Parameter.VAR_KEYWORD, inspect.Parameter.VAR_POSITIONAL)}
        result = call(**params)
        if inspect.isawaitable(result):
            await result
    assert len(observed) == len(methods) >= 20
    for method, path in observed:
        assert any(method == verb and re.fullmatch(pattern, path) for verb, pattern in routes()), (method, path)
