"""Tests for safe deterministic deployment rendering."""

import json
import stat
from pathlib import Path

import pytest

from mneme.cli import render_deployment as render_cli
from mneme.ops.deployment import (
    TEMPLATE_FILENAMES,
    DeploymentRenderConfig,
    DeploymentRenderError,
    render_deployment,
)

REPOSITORY_ROOT = Path(__file__).parents[2]
TEMPLATE_DIR = REPOSITORY_ROOT / "deploy" / "templates"


@pytest.mark.base
def test_renderer_produces_complete_deterministic_staging_tree(tmp_path: Path) -> None:
    config = DeploymentRenderConfig(server_name="api.mneme.example")
    output_dir = tmp_path / "rendered"

    first_paths = render_deployment(TEMPLATE_DIR, output_dir, config)
    first_bytes = {path.name: path.read_bytes() for path in first_paths}
    second_paths = render_deployment(TEMPLATE_DIR, output_dir, config)

    assert [path.name for path in first_paths] == [
        filename.removesuffix(".template") for filename in TEMPLATE_FILENAMES
    ]
    assert {path.name: path.read_bytes() for path in second_paths} == first_bytes
    assert stat.S_IMODE((output_dir / "backend.env").stat().st_mode) == 0o600
    assert stat.S_IMODE((output_dir / "mneme-api.service").stat().st_mode) == 0o644

    nginx = (output_dir / "nginx-mneme-tls.conf").read_text(encoding="utf-8")
    assert "server_name api.mneme.example;" in nginx
    assert "https://api.mneme.example$request_uri" in nginx
    assert "proxy_set_header X-Forwarded-For $remote_addr" in nginx
    assert 'proxy_set_header Connection ""' in nginx
    assert "${" not in nginx
    assert "ExecStart=/opt/mneme/backend/.venv/bin/gunicorn" in (
        output_dir / "mneme-api.service"
    ).read_text(encoding="utf-8")
    smoke_service = (output_dir / "mneme-smoke.service").read_text(encoding="utf-8")
    assert "python -m mneme.cli.smoke_backend" in smoke_service
    assert "--token-file /etc/mneme/demo.token" in smoke_service
    preflight_service = (output_dir / "mneme-preflight.service").read_text(encoding="utf-8")
    assert "python -m mneme.cli.preflight_deployment" in preflight_service
    assert "PGSERVICE=mneme-backup" in preflight_service
    assert "Requires=mneme-bootstrap.service" in preflight_service
    assert "Requires=mneme-migrate.service" in (output_dir / "mneme-worker.service").read_text(
        encoding="utf-8"
    )
    assert "KillSignal=SIGTERM" in (output_dir / "mneme-api.service").read_text(encoding="utf-8")
    assert "TimeoutStopSec=360" in (output_dir / "mneme-worker.service").read_text(encoding="utf-8")
    assert "TimeoutStartSec=2100" in (output_dir / "mneme-backup.service").read_text(
        encoding="utf-8"
    )
    assert "TimeoutStartSec=3900" in (output_dir / "mneme-seed.service").read_text(encoding="utf-8")
    assert "TimeoutStartSec=180" in (output_dir / "mneme-health.service").read_text(
        encoding="utf-8"
    )
    assert "Requires=mneme-worker.service" in (output_dir / "mneme-ingest.service").read_text(
        encoding="utf-8"
    )
    assert "OnCalendar=*-*-* 03:00:00 UTC" in (output_dir / "mneme-digest.timer").read_text(
        encoding="utf-8"
    )
    bootstrap_nginx = (output_dir / "nginx-mneme-bootstrap.conf").read_text(encoding="utf-8")
    assert "return 503;" in bootstrap_nginx
    assert "proxy_pass" not in bootstrap_nginx
    assert "ConditionPathExists" not in smoke_service


@pytest.mark.base
@pytest.mark.parametrize(
    "overrides",
    [
        {"server_name": "localhost"},
        {"server_name": "api.example.com."},
        {"server_name": "api.example.com\nBAD=1"},
        {"server_name": "api.example.com", "install_dir": Path("relative")},
        {"server_name": "api.example.com", "install_dir": Path("/home/mneme")},
        {"server_name": "api.example.com", "install_dir": Path("/opt/bad path")},
        {"server_name": "api.example.com", "install_dir": Path("/opt/bad%name")},
        {"server_name": "api.example.com", "install_dir": Path("/opt/bad\nname")},
        {"server_name": "api.example.com", "environment_file": Path("/tmp/backend.env")},
        {"server_name": "api.example.com", "paper_data_dir": Path("/tmp/papers")},
        {"server_name": "api.example.com", "backup_dir": Path("/tmp/backups")},
        {"server_name": "api.example.com", "service_user": "root user"},
        {"server_name": "api.example.com", "api_port": 443},
        {"server_name": "api.example.com", "api_workers": 9},
    ],
)
def test_render_config_rejects_unsafe_values(overrides: dict[str, object]) -> None:
    with pytest.raises(DeploymentRenderError):
        DeploymentRenderConfig(**overrides)  # type: ignore[arg-type]


@pytest.mark.base
def test_renderer_rejects_incomplete_or_symlinked_outputs(tmp_path: Path) -> None:
    incomplete = tmp_path / "templates"
    incomplete.mkdir()
    (incomplete / TEMPLATE_FILENAMES[0]).write_text("test", encoding="utf-8")
    config = DeploymentRenderConfig(server_name="api.example.com")

    with pytest.raises(DeploymentRenderError):
        render_deployment(incomplete, tmp_path / "output", config)

    output_link = tmp_path / "output-link"
    output_link.symlink_to(tmp_path / "elsewhere", target_is_directory=True)
    with pytest.raises(DeploymentRenderError):
        render_deployment(TEMPLATE_DIR, output_link, config)

    stale_output = tmp_path / "stale-output"
    stale_output.mkdir()
    (stale_output / "obsolete.service").write_text("stale", encoding="ascii")
    with pytest.raises(DeploymentRenderError):
        render_deployment(TEMPLATE_DIR, stale_output, config)


@pytest.mark.base
def test_render_cli_emits_stable_json(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    output_dir = tmp_path / "output"
    monkeypatch.setattr(
        "sys.argv",
        [
            "render_deployment",
            "--server-name",
            "api.example.com",
            "--template-dir",
            str(TEMPLATE_DIR),
            "--output-dir",
            str(output_dir),
        ],
    )

    render_cli.main()

    payload = json.loads(capsys.readouterr().out)
    assert payload["schema_version"] == "deployment-render-v1"
    assert payload["status"] == "ok"
    assert payload["files"] == sorted(
        filename.removesuffix(".template") for filename in TEMPLATE_FILENAMES
    )


@pytest.mark.base
def test_render_cli_default_template_path_is_cwd_independent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    output_dir = tmp_path / "output"
    monkeypatch.setattr(
        "sys.argv",
        [
            "render_deployment",
            "--server-name",
            "api.example.com",
            "--output-dir",
            str(output_dir),
        ],
    )

    render_cli.main()

    assert (output_dir / "mneme-api.service").is_file()


@pytest.mark.base
def test_render_cli_redacts_invalid_input(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    secret = "secret-api.example.com\nPASSWORD=do-not-print"
    monkeypatch.setattr(
        "sys.argv",
        ["render_deployment", "--server-name", secret, "--output-dir", str(tmp_path)],
    )

    with pytest.raises(SystemExit) as captured:
        render_cli.main()

    error = json.loads(capsys.readouterr().err)
    assert captured.value.code == 1
    assert error["error"] == render_cli.RENDER_ERROR
    assert "do-not-print" not in json.dumps(error)
