# TASK 04 — Config show/set commands

## Goal
Implement `execas config show` and `execas config set` so planning parameters are inspectable and modifiable.

## Depends on
- TASK 02 (schema + init seeds settings)

## In scope
- `execas config show` — prints all settings as key=value table.
- `execas config set <key> <value>` — updates a setting, validates key exists.
- Validation: reject unknown keys; type-check numeric values (e.g. buffer_min must be int >=0).

## Out of scope
- Planning algorithm (just settings CRUD).

## Files to touch (expected)
- apps/executive-cli/src/executive_cli/cli.py (config command group)
- apps/executive-cli/src/executive_cli/config.py (service layer)

## Acceptance checks (TEST_PLAN: T02)
- `execas config show` displays all 7 required keys with defaults.
- `execas config set buffer_min 10` persists; subsequent `config show` reflects change.
- `execas config set unknown_key foo` fails with clear error.

## Rollback
- Revert commit; settings table unaffected.
