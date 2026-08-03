"""CLI tests for the deployed MVP smoke runner."""

import json

import pytest

from mneme.cli import smoke_backend
from mneme.demo.smoke_types import MvpSmokeReport, SmokeCheck


@pytest.mark.base
def test_smoke_cli_emits_passing_report_without_token(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    secret = "raw-secret-token"
    captured: dict[str, object] = {}

    async def fake_run(config, *, token):
        captured["config"] = config
        captured["token"] = token
        return MvpSmokeReport(
            seed_arxiv_id=config.seed_arxiv_id,
            checks=(SmokeCheck("liveness", "passed"),),
        )

    monkeypatch.setenv("MNEME_MVP_SMOKE_TOKEN", secret)
    monkeypatch.setenv("MNEME_MVP_SMOKE_BASE_URL", "https://api.mneme.example")
    monkeypatch.setenv("MNEME_MVP_SMOKE_SEED", "https://arxiv.org/abs/1706.03762v7")
    monkeypatch.setattr(smoke_backend, "run_mvp_smoke", fake_run)
    monkeypatch.setattr("sys.argv", ["smoke_backend"])

    smoke_backend.main()

    streams = capsys.readouterr()
    payload = json.loads(streams.out)
    assert payload["status"] == "passed"
    assert payload["seed_arxiv_id"] == "1706.03762"
    assert captured["token"] == secret
    assert secret not in streams.out
    assert secret not in streams.err


@pytest.mark.base
def test_smoke_cli_returns_one_for_failed_acceptance(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    async def fake_run(config, *, token):
        del token
        return MvpSmokeReport(
            seed_arxiv_id=config.seed_arxiv_id,
            checks=(
                SmokeCheck(
                    "readiness",
                    "failed",
                    {"code": "unexpected_http_status", "status_code": 503},
                ),
            ),
        )

    monkeypatch.setenv("MNEME_MVP_SMOKE_TOKEN", "token")
    monkeypatch.setattr(smoke_backend, "run_mvp_smoke", fake_run)
    monkeypatch.setattr("sys.argv", ["smoke_backend"])

    with pytest.raises(SystemExit) as captured:
        smoke_backend.main()

    assert captured.value.code == 1
    assert json.loads(capsys.readouterr().out)["status"] == "failed"


@pytest.mark.base
def test_smoke_cli_returns_two_without_credentials(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.delenv("MNEME_MVP_SMOKE_TOKEN", raising=False)
    monkeypatch.delenv("MNEME_MVP_SMOKE_BASE_URL", raising=False)
    monkeypatch.setattr("sys.argv", ["smoke_backend"])

    with pytest.raises(SystemExit) as captured:
        smoke_backend.main()

    error = json.loads(capsys.readouterr().err)
    assert captured.value.code == 2
    assert error == {
        "error": smoke_backend.CONFIG_ERROR,
        "message": "MVP smoke configuration is invalid.",
        "status": "error",
    }


@pytest.mark.base
def test_smoke_cli_redacts_invalid_token(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    secret = "invalid token value"
    monkeypatch.setenv("MNEME_MVP_SMOKE_TOKEN", secret)
    monkeypatch.setattr("sys.argv", ["smoke_backend"])

    with pytest.raises(SystemExit) as captured:
        smoke_backend.main()

    streams = capsys.readouterr()
    assert captured.value.code == 2
    assert secret not in streams.out
    assert secret not in streams.err
