# Вопросы интервью — закрытие неопределённостей v2

> Максимум 12 вопросов. Каждый с ASSUMPTION-default, чтобы можно было двигаться без ответа.

---

### Q1. n8n: есть ли инстанс?

**Вопрос:** Есть ли уже запущенный n8n? Какая версия? Docker или системная установка?

**ASSUMPTION:** n8n нет. Поставим n8n self-hosted через Docker на неделе 3. Версия: latest stable.

**Влияние:** если n8n уже есть — пропускаем установку, адаптируем workflows под текущую версию.

---

### Q2. Alert channel: Telegram или email?

**Вопрос:** Куда отправлять алерты при сбое workflows (Ollama down, IMAP timeout, pipeline error)? Telegram бот? Email? Оба?

**ASSUMPTION:** Telegram бот. Один канал. Email-алерты избыточны (мы и так читаем email через IMAP).

**Влияние:** определяет n8n notification node (Telegram vs Email vs HTTP webhook).

---

### Q3. Yandex IMAP: какой аккаунт?

**Вопрос:** Используется один email-аккаунт или несколько? Нужна ли фильтрация по mailbox/label (INBOX only, или все папки)?

**ASSUMPTION:** один аккаунт, только INBOX. Фильтрация по папкам — post-MVP.

**Влияние:** определяет IMAP `EXAMINE INBOX` vs `EXAMINE *`. Несколько аккаунтов = несколько IMAP connectors.

---

### Q4. CalDAV: Yandex Calendar или другой?

**Вопрос:** CalDAV подключается к Yandex Calendar? Или Google Calendar / Apple Calendar? Один календарь или несколько?

**ASSUMPTION:** Yandex Calendar, один основной календарь. CalDAV URL: `https://caldav.yandex.ru`.

**Влияние:** CalDAV endpoint, auth method (app password vs OAuth), количество `calendars` записей.

---

### Q5. Ollama: уже установлен?

**Вопрос:** Ollama уже установлен? Модель `qwen2.5:7b` скачана? Достаточно ли RAM (минимум 8 GB для 7B модели)?

**ASSUMPTION:** Ollama установлен, `qwen2.5:7b` доступна. Если нет — установка `brew install ollama && ollama pull qwen2.5:7b`.

**Влияние:** если Ollama не стоит — добавляем setup-шаг на неделе 1.

---

### Q6. Anthropic API key: есть?

**Вопрос:** Есть ли `ANTHROPIC_API_KEY` для fallback? Какой тарифный план (бюджет на fallback вызовы)?

**ASSUMPTION:** ключ есть, бюджет $5-10/мес. Fallback срабатывает редко (Ollama покрывает 90%+).

**Влияние:** если ключа нет — fallback = local heuristic only. Quality degradation при Ollama downtime.

---

### Q7. Сколько emails в день?

**Вопрос:** Типичное количество новых email в INBOX за рабочий день? 10? 50? 200?

**ASSUMPTION:** 30-50 emails/day. Это определяет: 30-50 LLM-вызовов/day (Ollama), ~10 минут total processing.

**Влияние:** если 200+/day — нужен rate limiting, batch processing, возможно кеш prompt-хешей. Если 10/day — всё тривиально.

---

### Q8. PII в subject: стрипать?

**Вопрос:** Нужно ли удалять PII (имена, телефоны, email-адреса) из subject перед отправкой в Ollama (локальная LLM)?

**ASSUMPTION:** нет. Ollama = local, данные не покидают машину. PII stripping только при отправке в Anthropic API (облако).

**Влияние:** если да — добавляем regex-based PII stripping в llm_gateway перед cloud fallback.

---

### Q9. day_plans + time_blocks: нужны?

**Вопрос:** Planner записывает результат в `day_plans` + `time_blocks`. Нужна ли эта персистенция, или достаточно вывода в CLI?

**ASSUMPTION:** да, сохраняем. Planner уже пишет туда, и это полезно для `execas dash` (история планов).

**Влияние:** если нет — удаляем 2 таблицы, planner возвращает результат без записи. Итого 12 таблиц → 10.

---

### Q10. Existing tasks: сколько данных в v1?

**Вопрос:** Сколько записей в текущей v1 SQLite? Tasks? Projects? Areas? Нужен ли автоматический скрипт миграции?

**ASSUMPTION:** < 500 tasks, < 20 projects, < 10 areas. Ручной `sqlite3 .dump` достаточен.

**Влияние:** если 5000+ записей — нужен скрипт `migrate_v1_to_v2.py` с маппингом полей.

---

### Q11. Webhook для email trigger?

**Вопрос:** Нужен ли n8n webhook для on-demand email ingest (POST `/api/ingest-email`), или достаточно cron (07:00 daily)?

**ASSUMPTION:** достаточно cron. On-demand можно запустить из CLI: `execas ingest email --since today`.

**Влияние:** если нужен webhook — добавляем Workflow #2 (Email Ingest On-Demand) в n8n на неделе 3.

---

### Q12. Audit log для approve/reject?

**Вопрос:** Нужен ли отдельный audit log для approve/reject решений, или `task_drafts.reviewed_at` + `task_drafts.status` достаточно?

**ASSUMPTION:** `task_drafts.reviewed_at` + `status` достаточно. Отдельная таблица audit_log — over-engineering для single-user.

**Влияние:** если нужен audit — добавляем таблицу `approval_audit` (13-я таблица). Записывается при каждом approve/reject.

---

## Сводка ASSUMPTION defaults

| # | Вопрос | Default |
|---|--------|---------|
| Q1 | n8n | Нет, поставим Docker |
| Q2 | Alert | Telegram бот |
| Q3 | IMAP | 1 аккаунт, INBOX only |
| Q4 | CalDAV | Yandex Calendar, 1 календарь |
| Q5 | Ollama | Установлен, qwen2.5:7b |
| Q6 | Anthropic key | Есть, $5-10/мес |
| Q7 | Email volume | 30-50/day |
| Q8 | PII strip | Нет для local, да для cloud |
| Q9 | day_plans | Сохраняем |
| Q10 | Data volume | < 500 records, manual dump |
| Q11 | Webhook | Не нужен, cron + CLI |
| Q12 | Audit log | task_drafts.reviewed_at достаточно |

**Если все ASSUMPTION приняты — можно начинать неделю 1 без дополнительных ответов.**
