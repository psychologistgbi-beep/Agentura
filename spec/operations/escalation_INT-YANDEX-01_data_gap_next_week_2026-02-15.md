# Эскалация: INT-YANDEX-01 (data gap в `calendar next-week`)

**Роль:** Executive Assistant (EA)  
**Кому:** Technical Lead  
**Дата:** 2026-02-15  
**Приоритет:** P1  
**Статус:** Triage завершен TL, передано в реализацию EA

## Инцидент

Обнаружено расхождение между фактическим календарем пользователя и локальным выводом CLI:

- `uv run execas sync hourly --retries 2 --backoff-sec 5` -> `status=ok` (calendar ok, mail ok)
- `uv run execas calendar next-week --source yandex_caldav` -> `No meetings found for next week`
- Пользователь предоставил скриншот календаря на неделю `2026-02-16..2026-02-22` с множеством встреч.

Итог: синхронизация формально успешна, но пользовательский результат пустой (ложно-отрицательный вывод по встречам).

## Влияние

- Нельзя доверять отчету `next-week` для планирования.
- Риск пропуска рабочих встреч в ежедневном плане.
- Интеграция воспринимается как нестабильная при `status=ok`.

## Факты/контекст

1. Ранее наблюдались auth-блокеры, но в последнем прогоне оба источника прошли успешно.
2. Почта синхронизируется инкрементально (`mail sync --this-year`), курсор сохранен.
3. Для календаря `calendar sync` завершается успешно, но данных в срезе следующей недели нет.

## Гипотезы причин (для TL triage)

1. Неверный CalDAV collection/principal: синк идет в пустой календарь, а не в рабочий основной календарь пользователя.
2. Ошибка фильтра временного окна в `calendar next-week` (локальная TZ/границы интервала).
3. Некорректный парсинг части VEVENT (повторяющиеся события, all-day, DTSTART/DTEND edge-cases).
4. События попадают в БД с `source != yandex_caldav` или с `is_deleted=1`.

## Запрос к Technical Lead

1. Запустить расследование расхождения данных как P1 functional incident.
2. Назначить владельца на проверку:
   - источника/URL календарной коллекции;
   - корректности фильтра `next-week`;
   - соответствия sync result фактическим вставкам в `busy_blocks`.
3. Подготовить фикс и regression-тест(ы), покрывающие случай: встречи есть в реальном календаре -> не пустой `next-week`.

## Минимальный диагностический пакет (рекомендуемый TL)

```bash
cd /Users/gaidabura/Agentura/apps/executive-cli
uv run execas calendar sync
uv run execas calendar next-week --source yandex_caldav

# Проверка фактических строк в БД за ту же неделю
sqlite3 .data/execas.sqlite "
SELECT id, source, is_deleted, start_dt, end_dt, title
FROM busy_blocks
WHERE source='yandex_caldav'
ORDER BY start_dt
LIMIT 200;
"
```

Критерий подтверждения инцидента: `next-week` пустой при наличии релевантных строк `busy_blocks` в целевом диапазоне или при наличии встреч в внешнем календаре пользователя.

## TL P1 triage (2026-02-15)

### Назначение владельца реализации

- **Implementation owner:** Executive Assistant (INT-EXEC-01 lane).
- **QA owner (regression):** QA/SET (INT-QA-01 lane).
- **TL owner:** контроль SLA, приемка фикса и обновление acceptance ledger.

### Root-cause shortlist (приоритет)

1. **CalDAV collection mismatch (наиболее вероятно):** `EXECAS_CALDAV_URL` указывает на principal/коллекцию без рабочих событий, sync завершается успешно, но возвращает пустой snapshot.
2. **Soft-delete side effect при full snapshot:** при пустом/неполном snapshot события источника помечаются `is_deleted=1`, после чего `next-week` закономерно пустой.
3. **Фильтрация окна next-week vs timezone setting:** границы окна вычисляются по `Settings.timezone`; при неправильной TZ в настройках возможна потеря части событий в диапазоне.
4. **VEVENT parsing gaps:** часть событий может отбрасываться парсером из-за edge-cases в `DTSTART/DTEND/RECURRENCE-ID` и не доходить до `busy_blocks`.
5. **Source/is_deleted mismatch в данных:** записи есть, но не проходят фильтр `source='yandex_caldav' AND is_deleted=0`.

### Диагностический план (P1)

1. Подтвердить текущий симптом:
   ```bash
   cd /Users/gaidabura/Agentura/apps/executive-cli
   uv run execas calendar sync
   uv run execas calendar next-week --source yandex_caldav --anchor-date 2026-02-15
   ```
2. Проверить фактическое содержимое `busy_blocks` и soft-delete:
   ```bash
   sqlite3 .data/execas.sqlite "
   SELECT source, is_deleted, COUNT(*) FROM busy_blocks GROUP BY source, is_deleted;
   SELECT id, source, is_deleted, start_dt, end_dt, title, external_id
   FROM busy_blocks
   WHERE source='yandex_caldav'
   ORDER BY start_dt
   LIMIT 300;
   "
   ```
3. Проверить состояние курсора календаря:
   ```bash
   sqlite3 .data/execas.sqlite "
   SELECT source, scope, cursor_kind, cursor, updated_at
   FROM sync_state
   WHERE source='yandex_caldav';
   "
   ```
4. Сверить endpoint/коллекцию CalDAV с пользователем (principal vs calendar collection URL).
5. Если в БД есть строки на неделю `2026-02-16..2026-02-22`, а команда все еще пустая, фиксировать дефект фильтра `next-week`; если строк нет, фокус на connector/snapshot path.

### Fix scope (ограниченный P1)

- Добавить диагностическую прозрачность после `calendar sync`: явный output по количеству активных `yandex_caldav` блоков и предупреждение при аномалии `0 active rows`.
- Защитить от ложного "ok" при пустом snapshot: в явном виде помечать degraded/suspect path (без расширения scope на schema/ADR).
- Проверить и при необходимости скорректировать обработку full snapshot/soft-delete, чтобы не терять валидные события из-за неполной коллекции.
- Уточнить operational инструкцию по правильному CalDAV collection URL.

### Regression-test scope

- `tests/test_calendar_next_week.py`:
  - кейс с данными в target week обязан возвращать непустой список для `--source yandex_caldav`;
  - кейс TZ boundary (событие около полуночи в локальной зоне).
- `tests/test_calendar_sync.py`:
  - кейс full snapshot empty/non-empty и корректность `soft_deleted`;
  - кейс, где sync не должен маскировать аномально пустой календарный результат как обычный success.
- Smoke:
  - `uv run execas calendar sync`
  - `uv run execas calendar next-week --source yandex_caldav --anchor-date 2026-02-15`

### SLA, статус, checkpoint

- **SLA:** P1 triage завершить в день инцидента (2026-02-15), owner fix plan + первые диагностические результаты до `2026-02-15 23:30 MSK`.
- **Текущий статус:** `in_progress (implementation assigned)`.
- **Следующий checkpoint:** `2026-02-15 23:30 MSK` — EA публикует диагностические результаты и delta-план фикса, TL обновляет dispatch verdict/status.
