# D5. WORKFLOWS_N8N — n8n как оркестратор

> n8n вызывает CLI по shell/exec или HTTP webhook. n8n НЕ вызывает LLM напрямую.
> Вся бизнес-логика — внутри Python CLI. n8n = trigger + retry + error handling + scheduling.

## 1. Workflow: Daily GTD (cron)

**Trigger:** Cron `0 7 * * 1-5` (пн-пт 07:00) + manual trigger

**Шаги:**

```
[Cron 07:00] → [Execute: execas daily --date today --variant realistic]
              → [Check exit code]
              → exit 0 → [Log success]
              → exit != 0 → [Wait 5min] → [Retry 1] → [Retry 2] → [Alert: Telegram/email]
```

**n8n nodes:**
1. `Cron Trigger` — schedule
2. `Execute Command` — `cd /path && uv run execas daily --date $(date +%Y-%m-%d)`
3. `IF` — exit code == 0?
4. `Wait` — 5 min on failure
5. `Execute Command` — retry (max 2 retries)
6. `Telegram/Email` — alert on final failure

**Idempotency:** `execas daily` проверяет `ingest_documents.source_ref` перед повторной обработкой email. Повторный запуск = безопасен.

**Лог:** stdout CLI содержит summary. n8n сохраняет execution log.

---

## 2. Workflow: Email Ingest On-Demand

**Trigger:** Webhook POST `/api/ingest-email` или manual

**Шаги:**

```
[Webhook] → [Execute: execas ingest email --since YYYY-MM-DD --limit 20]
           → [Parse stdout → JSON]
           → [IF auto_created > 0 → Telegram notify]
           → [IF drafted > 0 → Telegram: "N drafts pending, run approve batch"]
```

**n8n nodes:**
1. `Webhook Trigger` — POST, optional `?since=2026-02-18&limit=20`
2. `Execute Command` — `execas ingest email --since {{$json.since}} --limit {{$json.limit}}`
3. `Function` — parse stdout lines → JSON `{processed, auto_created, drafted, skipped}`
4. `IF` — auto_created > 0 or drafted > 0
5. `Telegram` (optional) — notify

**Idempotency:** `(channel, source_ref)` unique в `ingest_documents`. Safe to re-run.

---

## 3. Workflow: Approval Reminder

**Trigger:** Cron `0 9,14 * * 1-5` (9:00 и 14:00 рабочих дней)

**Шаги:**

```
[Cron] → [Execute: execas approve batch --limit 0]
       → [Parse: count pending from stdout]
       → [IF pending > 0 → Telegram: "You have N pending drafts"]
```

ASSUMPTION: `execas approve batch --limit 0` prints "No pending approvals." or count without interactive mode. Альтернатива: отдельная команда `execas approve count`.

**Idempotency:** read-only, безопасен.

---

## 4. Workflow: LLM Log Cleanup

**Trigger:** Cron `0 3 * * 0` (воскресенье 03:00)

**Шаги:**

```
[Cron] → [Execute: sqlite3 /path/execas.sqlite "DELETE FROM llm_call_log WHERE created_at < datetime('now', '-30 days')"]
       → [Execute: sqlite3 /path/execas.sqlite "DELETE FROM ingest_log WHERE created_at < datetime('now', '-90 days')"]
       → [Log: deleted N rows]
```

**Idempotency:** DELETE WHERE date < X — idempotent.

---

## 5. Общие правила для всех workflows

| Правило | Значение |
|---------|----------|
| Max retries | 2 |
| Retry delay | 5 min (exponential: 5, 10) |
| Timeout per step | 120s |
| Alert channel | Telegram бот (отдельный аккаунт ассистента) |
| Error handling | n8n catch → alert → stop workflow |
| Secrets | n8n credentials store, не env vars внутри workflow JSON |
| Execution log | n8n built-in, retention 30 days |

## Open questions

Нет. Все решения приняты:
1. n8n — нет, поставим Docker на неделе 3
2. Alert channel — Telegram бот (отдельный аккаунт для ассистента)
3. Webhook — default: cron + CLI. Webhook можно добавить позже
