from __future__ import annotations

import os
import subprocess

DEFAULT_CALDAV_KEYCHAIN_SERVICE = "execas.caldav.password"
DEFAULT_IMAP_KEYCHAIN_SERVICE = "execas.imap.password"


class SecretStoreError(RuntimeError):
    """Raised when a keychain operation fails."""


def resolve_keychain_service(env_var: str, default: str) -> str:
    value = os.getenv(env_var, "").strip()
    return value or default


def load_password_from_keychain(
    *,
    account: str,
    env_service_var: str,
    default_service: str,
) -> str | None:
    account_value = account.strip()
    if not account_value:
        return None
    service = resolve_keychain_service(env_service_var, default_service)
    return keychain_password_lookup(service=service, account=account_value)


def keychain_password_lookup(*, service: str, account: str) -> str | None:
    service_value = service.strip()
    account_value = account.strip()
    if not service_value or not account_value:
        return None

    try:
        completed = subprocess.run(
            ["security", "find-generic-password", "-s", service_value, "-a", account_value, "-w"],
            check=False,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        return None

    if completed.returncode != 0:
        return None

    value = (completed.stdout or "").strip()
    return value or None


def keychain_password_exists(*, service: str, account: str) -> bool:
    return keychain_password_lookup(service=service, account=account) is not None


def store_keychain_password(*, service: str, account: str, password: str) -> None:
    service_value = service.strip()
    account_value = account.strip()
    if not service_value:
        raise SecretStoreError("Keychain service name must not be empty.")
    if not account_value:
        raise SecretStoreError("Keychain account must not be empty.")
    if not password:
        raise SecretStoreError("Password must not be empty.")

    try:
        completed = subprocess.run(
            [
                "security",
                "add-generic-password",
                "-U",
                "-s",
                service_value,
                "-a",
                account_value,
                "-w",
                password,
            ],
            check=False,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as exc:
        raise SecretStoreError("macOS Keychain CLI is unavailable on this machine.") from exc

    if completed.returncode != 0:
        stderr = (completed.stderr or "").strip()
        raise SecretStoreError(
            f"Failed to store secret in Keychain service '{service_value}' for account '{account_value}'. {stderr}"
        )
