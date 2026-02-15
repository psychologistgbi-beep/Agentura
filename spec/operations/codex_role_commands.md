# Codex Role Commands

This project provides a role launcher for Codex CLI:

- `/Users/gaidabura/Agentura/scripts/codex-role`
- `/Users/gaidabura/Agentura/scripts/codex-role-aliases.sh`

## Enable shortcuts

```bash
cd /Users/gaidabura/Agentura
source scripts/codex-role-aliases.sh
```

## Interactive role sessions

```bash
codex_tl "Согласуй план на спринт и выдай task briefs."
codex_ca "Сделай architecture review по ARCH-ALIGN задаче."
codex_ea "Реализуй задачу из spec/TASKS и приложи gate report."
codex_dh "Декомпозируй TECH_SPEC в задачи."
codex_bc "Дай рекомендации по приоритетам на неделю."
codex_sa "Подготовь требования и acceptance criteria для Sprint Goal."
codex_po "Приоритизируй backlog на ближайший спринт."
codex_sm "Проведи sprint health check и зафиксируй блокеры."
codex_qa "Подготовь quality verdict по release scope."
codex_sre "Проверь CI/release readiness и runbook риски."
```

## Role sessions with explicit skills

```bash
codex-role sa --skill agentura-sa-integration-dor "Подготовь DoR для новой интеграции."
codex-role ea --skill agentura-ea-yandex-live-run "Выполни live-run интеграции и оформи evidence."
codex-role qa --skill agentura-qa-timezone-redaction "Проверь timezone и redaction в интеграционном потоке."
codex-role sre --skill agentura-sre-hourly-sanity-alert "Проведи ops readiness и политику алертов."
codex-role tl --skill agentura-tl-acceptance-ledger "Прими/отклони коммиты и обнови ledger."
codex-role sm --skill agentura-sm-lane-sla-wip "Проверь SLA блокеров и WIP lane лимиты."
```

## Non-interactive role runs

```bash
codex_tl_exec "Проверь gate reports, прими коммиты и подготовь push plan."
codex_ea_exec "Выполни OPS-02 по задаче и верни 7-section report."
codex_sa_exec "Уточни требования и обнови traceability для задачи."
codex_qa_exec "Запусти quality gates и верни release verdict."
```

## Notes

- Launcher injects role context using `AGENTS.md`, role `SKILL.md`, and `spec/templates/PREFLIGHT_STAMP_TEMPLATE.md`.
- Project Codex skills catalog: `/Users/gaidabura/Agentura/.agents/skills`.
- Skill inventory helper: `/Users/gaidabura/Agentura/scripts/codex-skills-check`.
- `Technical Lead` has guarded push authority per `AGENTS.md` section 7.
- For implementation tasks, role `SKILL.md` discovery (R2) is mandatory.
- Team standards reference: `spec/TEAM_STANDARDS.md`.
