#!/usr/bin/env bash

_codex_role_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
_codex_role_cmd="${_codex_role_dir}/codex-role"

codex_tl() { "${_codex_role_cmd}" tl "$@"; }
codex_ca() { "${_codex_role_cmd}" ca "$@"; }
codex_ea() { "${_codex_role_cmd}" ea "$@"; }
codex_dh() { "${_codex_role_cmd}" dh "$@"; }
codex_bc() { "${_codex_role_cmd}" bc "$@"; }

codex_tl_exec() { "${_codex_role_cmd}" tl --exec "$@"; }
codex_ca_exec() { "${_codex_role_cmd}" ca --exec "$@"; }
codex_ea_exec() { "${_codex_role_cmd}" ea --exec "$@"; }
codex_dh_exec() { "${_codex_role_cmd}" dh --exec "$@"; }
codex_bc_exec() { "${_codex_role_cmd}" bc --exec "$@"; }
