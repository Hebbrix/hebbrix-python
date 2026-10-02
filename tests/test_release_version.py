"""Prevent package identity from drifting from either HTTP transport."""
import inspect
import re

import hebbrix
from hebbrix import client, sync_client


def test_both_transport_versions_match_package():
    for module in (client, sync_client):
        versions = re.findall(r'hebbrix-python/([^\s\"\x27]+)', inspect.getsource(module))
        assert versions == [hebbrix.__version__]
