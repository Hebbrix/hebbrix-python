"""Prevent package identity from drifting from either HTTP transport."""
import inspect
import re

import hebbrix
from hebbrix import client, sync_client


def test_both_transport_versions_match_package():
    for module in (client, sync_client):
        versions = re.findall(r'hebbrix-python/([^\s\"\x27]+)', inspect.getsource(module))
        assert versions == [hebbrix.__version__]


def test_runtime_httpx_is_bounded_below_breaking_major():
    from pathlib import Path
    from packaging.requirements import Requirement
    text = (Path(__file__).resolve().parents[1] / "pyproject.toml").read_text()
    requirement = Requirement(re.search(r'"(httpx[^"\n]+)"', text).group(1))
    assert requirement.specifier.contains("0.28.1")
    assert not requirement.specifier.contains("1.0.dev6", prereleases=True)
    assert not requirement.specifier.contains("1.0.0")
