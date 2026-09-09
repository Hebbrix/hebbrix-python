import json

import pytest
from hebbrix import reflection_worker as cli
from hebbrix.workflow import ReflectionUncertain

ARGS = ["--program", "program", "--request-key", "stable-attempt",
        "--input-rate-ceiling", "1.75", "--output-rate-ceiling", "14"]


def test_help_needs_no_credential_or_provider_call(monkeypatch, capsys):
    monkeypatch.delenv("HEBBRIX_REFLECTION_KEY", raising=False)
    with pytest.raises(SystemExit) as exc:
        cli.main(["--help"])
    assert exc.value.code == 0
    assert "--request-key" in capsys.readouterr().out


def test_missing_credential_is_a_redacted_configuration_failure(monkeypatch, capsys):
    monkeypatch.delenv("HEBBRIX_REFLECTION_KEY", raising=False)
    with pytest.raises(SystemExit) as exc:
        cli.main(ARGS)
    assert exc.value.code == 1
    assert json.loads(capsys.readouterr().out) == {
        "status": "configuration_or_workflow_failure", "automatic_retry": False,
    }


@pytest.mark.parametrize("uncertain", [False, True])
def test_cli_never_discloses_provider_or_cleanup_errors(monkeypatch, capsys, uncertain):
    marker = "private-key-that-must-never-be-printed"
    monkeypatch.setenv("HEBBRIX_REFLECTION_KEY", marker)
    calls = []

    class Client:
        experiences = object()

        def __init__(self, **kwargs):
            assert kwargs["api_key"] == marker

        def close(self):
            calls.append("close")
            raise RuntimeError(marker)

    class Worker:
        def __init__(self, resource):
            pass

        def run_once(self, program, **kwargs):
            calls.append(kwargs["request_key"])
            if uncertain:
                raise ReflectionUncertain("job", "dispatch")
            raise RuntimeError(marker)

    monkeypatch.setattr(cli, "SyncMemoryClient", Client)
    monkeypatch.setattr(cli, "ReflectionWorker", Worker)
    with pytest.raises(SystemExit) as exc:
        cli.main(ARGS)
    assert exc.value.code == (2 if uncertain else 1)
    captured = capsys.readouterr()
    assert marker not in captured.out + captured.err
    assert calls == ["stable-attempt", "close"]
    if uncertain:
        assert json.loads(captured.out)["job_id"] == "job"
