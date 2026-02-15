# Эскалация: INT-YANDEX-01 (auth для CalDAV/IMAP)

**Роль:** Executive Assistant (EA)  
**Кому:** Technical Lead  
**Дата:** 2026-02-15  
**Статус:** Передано TL

## Тема: Эскалация блокера INT-YANDEX-01 (auth для CalDAV/IMAP)

Нужна помощь TL по интеграции рабочей почты/календаря (ООО «Цифровые сервисы», `gaydabura@myservices.digital`).

Что уже проверено:
1. Локальный CLI и коннекторы рабочие (`execas calendar sync`, `execas mail sync` запускаются корректно).
2. Сеть/SSL до IMAP доступна:
- `imap.yandex.com:993` — TLS OK
- `imap.ya.ru:993` — TLS OK
3. `https://caldav.yandex.ru` доступен, но отвечает `401 Unauthorized` на PROPFIND.
4. В live-прогонах `scripts/ea-yandex-check --only-smoke` стабильно:
- `caldav_auth_failed status=401`
- `calendar_sync_failed source=yandex_caldav scope=primary stage=fetch`
5. Пользователь создал app-password для почты (IMAP). Для календаря использовался отдельный пароль CalDAV, но `401` сохраняется.

Вывод:
- Блокер не в коде/сети, а в auth/policy Yandex 360 для домена `myservices.digital` (или в требуемом CalDAV principal/collection URL).

Что нужно от TL:
1. Скоординировать с админом домена проверку политик доступа:
- включены ли IMAP и CalDAV для пользователя;
- разрешены ли app-passwords для Mail и Calendar.
2. Уточнить/получить точный CalDAV endpoint (principal/collection URL) для этого аккаунта.
3. После подтверждения политик — дать команду на повторный acceptance-прогон:
- `uv run execas calendar sync`
- `uv run execas mail sync --mailbox INBOX`
- `uv run execas sync hourly --retries 2 --backoff-sec 5`
- `uv run execas calendar next-week --source yandex_caldav`
