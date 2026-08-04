"""CLI contract tests for reproducible demo preparation."""

import json

import pytest

from mneme.cli import seed_demo as seed_cli
from mneme.demo.seeding_support import DemoSeedResult


@pytest.mark.base
def test_demo_seed_dry_run_avoids_settings_and_external_state(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        seed_cli,
        "get_settings",
        lambda: (_ for _ in ()).throw(AssertionError("settings must not load")),
    )
    monkeypatch.setattr("sys.argv", ["seed_demo", "--dry-run"])

    seed_cli.main()

    payload = json.loads(capsys.readouterr().out)
    assert payload["schema_version"] == "demo-seed-plan-v1"
    assert payload["status"] == "dry_run"
    assert payload["paper_count"] == 5
    assert payload["event_count"] == 8


@pytest.mark.base
def test_demo_seed_cli_prints_safe_result(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    result = DemoSeedResult(
        manifest_id="mneme-live-core-v1",
        manifest_sha256="a" * 64,
        digest_id="00000000-0000-0000-0000-000000000099",
        seed_paper_id="00000000-0000-0000-0000-000000000100",
        digest_paper_ids=("00000000-0000-0000-0000-000000000001",),
        digest_arxiv_ids=("2401.00001",),
        paper_count=5,
        ready_papers=5,
        partial_papers=0,
        events_accepted=8,
        events_duplicates=0,
        user_created=True,
        preferences_created=True,
    )

    async def successful(*_args: object, **_kwargs: object) -> DemoSeedResult:
        return result

    monkeypatch.setattr(seed_cli, "get_settings", lambda: object())
    monkeypatch.setattr(seed_cli, "read_private_demo_token", lambda *_args: "raw-secret")
    monkeypatch.setattr(seed_cli, "seed_demo", successful)
    monkeypatch.setattr("sys.argv", ["seed_demo"])

    seed_cli.main()

    payload = json.loads(capsys.readouterr().out)
    assert payload["schema_version"] == "demo-seed-result-v1"
    assert payload["status"] == "ok"
    assert payload["seed_paper_id"] == "00000000-0000-0000-0000-000000000100"
    assert payload["digest_arxiv_ids"] == ["2401.00001"]
    assert payload["ready_papers"] == 5
    assert payload["partial_papers"] == 0
    assert "raw-secret" not in json.dumps(payload)


@pytest.mark.base
def test_demo_seed_cli_redacts_runtime_failure(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    async def failed(*_args: object, **_kwargs: object) -> DemoSeedResult:
        raise seed_cli.DemoSeedError("raw-secret-token")

    monkeypatch.setattr(seed_cli, "get_settings", lambda: object())
    monkeypatch.setattr(seed_cli, "read_private_demo_token", lambda *_args: "raw-secret")
    monkeypatch.setattr(seed_cli, "seed_demo", failed)
    monkeypatch.setattr("sys.argv", ["seed_demo"])

    with pytest.raises(SystemExit) as captured:
        seed_cli.main()

    payload = json.loads(capsys.readouterr().err)
    assert captured.value.code == 1
    assert payload["error"] == seed_cli.SEED_ERROR
    assert "secret" not in json.dumps(payload)
