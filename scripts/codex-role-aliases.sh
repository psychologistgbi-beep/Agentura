#!/usr/bin/env bash

_codex_role_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
_codex_role_cmd="${_codex_role_dir}/codex-role"

codex_tl() { "${_codex_role_cmd}" tl "$@"; }
codex_ca() { "${_codex_role_cmd}" ca "$@"; }
codex_ea() { "${_codex_role_cmd}" ea "$@"; }
codex_dh() { "${_codex_role_cmd}" dh "$@"; }
codex_bc() { "${_codex_role_cmd}" bc "$@"; }
codex_sa() { "${_codex_role_cmd}" sa "$@"; }
codex_po() { "${_codex_role_cmd}" po "$@"; }
codex_sm() { "${_codex_role_cmd}" sm "$@"; }
codex_qa() { "${_codex_role_cmd}" qa "$@"; }
codex_sre() { "${_codex_role_cmd}" sre "$@"; }

codex_tl_exec() { "${_codex_role_cmd}" tl --exec "$@"; }
codex_ca_exec() { "${_codex_role_cmd}" ca --exec "$@"; }
codex_ea_exec() { "${_codex_role_cmd}" ea --exec "$@"; }
codex_dh_exec() { "${_codex_role_cmd}" dh --exec "$@"; }
codex_bc_exec() { "${_codex_role_cmd}" bc --exec "$@"; }
codex_sa_exec() { "${_codex_role_cmd}" sa --exec "$@"; }
codex_po_exec() { "${_codex_role_cmd}" po --exec "$@"; }
codex_sm_exec() { "${_codex_role_cmd}" sm --exec "$@"; }
codex_qa_exec() { "${_codex_role_cmd}" qa --exec "$@"; }
codex_sre_exec() { "${_codex_role_cmd}" sre --exec "$@"; }
