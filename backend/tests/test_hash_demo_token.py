"""Tests for the shell-history-safe demo-token digest command."""

import pytest

from mneme.cli import hash_demo_token
from mneme.core.security import token_sha256


@pytest.mark.base
def test_hash_nonempty_token_matches_security_helper() -> None:
    assert hash_demo_token.hash_nonempty_token("secret") == token_sha256("secret")


@pytest.mark.base
def test_cli_prints_digest_without_echoing_token(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    raw_token = "do-not-echo-this-token"
    monkeypatch.setattr(hash_demo_token.getpass, "getpass", lambda _: raw_token)

    hash_demo_token.main()

    captured = capsys.readouterr()
    assert captured.out.strip() == token_sha256(raw_token)
    assert raw_token not in captured.out
    assert raw_token not in captured.err


@pytest.mark.base
def test_cli_rejects_empty_token(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(hash_demo_token.getpass, "getpass", lambda _: "")

    with pytest.raises(SystemExit) as captured:
        hash_demo_token.main()

    assert captured.value.code == 2
    assert capsys.readouterr().err.strip() == "Demo token must not be empty"
