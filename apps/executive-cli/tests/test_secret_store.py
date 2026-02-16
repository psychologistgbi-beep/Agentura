from __future__ import annotations

import subprocess

import pytest

from executive_cli.secret_store import (
    SecretStoreError,
    keychain_password_lookup,
    store_keychain_password,
)


def test_keychain_password_lookup_returns_secret(monkeypatch) -> None:
    def _run(*args, **kwargs):
        del args, kwargs
        return subprocess.CompletedProcess(args=[], returncode=0, stdout="token-123\n", stderr="")

    monkeypatch.setattr("executive_cli.secret_store.subprocess.run", _run)

    value = keychain_password_lookup(service="svc", account="acc")
    assert value == "token-123"


def test_keychain_password_lookup_returns_none_when_missing(monkeypatch) -> None:
    def _run(*args, **kwargs):
        del args, kwargs
        return subprocess.CompletedProcess(args=[], returncode=44, stdout="", stderr="not found")

    monkeypatch.setattr("executive_cli.secret_store.subprocess.run", _run)

    value = keychain_password_lookup(service="svc", account="acc")
    assert value is None


def test_store_keychain_password_raises_on_failure(monkeypatch) -> None:
    def _run(*args, **kwargs):
        del args, kwargs
        return subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr="denied")

    monkeypatch.setattr("executive_cli.secret_store.subprocess.run", _run)

    with pytest.raises(SecretStoreError, match="Failed to store secret"):
        store_keychain_password(service="svc", account="acc", password="secret")
