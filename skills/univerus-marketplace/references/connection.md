# Подключение и контракт

Публичная документация: [быстрый старт](https://univerus.ai/docs/api/quickstart.md), [инструкция API](https://univerus.ai/docs/api/skill.md), [OpenAPI](https://univerus.ai/api/v1/openapi.json).

## MCP и OAuth

Клиентский endpoint: `https://univerus.ai/api/mcp/marketplace` (для другого стенда используй его доверенный origin). Транспорт Streamable HTTP. Четыре инструмента: `account_access`, `marketplace_categories`, `marketplace_orders(filters)`, `marketplace_order(order_id)`. Клиент должен поддерживать OAuth discovery, DCR public client и Authorization Code с PKCE S256; scope `marketplace:read`. Вход и явное согласие проходят на сайте Универус. Не обменивай коды и токены вручную в чате.

Обновлением токенов занимается клиент. По текущему контракту access token действует 15 минут, подключение — до 30 дней от авторизации; затем нужен повторный вход. Потеря продуктового доступа или отзыв подключения закрывают чтение. Отозвать подключение можно в настройках аккаунта («API и агенты», API управления `/api/account/connections`).

Общий `/api/mcp` также принимает персональный ключ в заголовке `Authorization: Bearer …`, если клиент поддерживает безопасную настройку заголовков. Для пользователя биржи предпочтителен отдельный endpoint с OAuth.

## HTTP и локальный скрипт

Создай персональный ключ `uvp_` с областью `marketplace:read` в `/settings?tab=api-agents`. Управление ключами — браузерный `/api/account/api-keys`, не внешний API. Секрет показывается один раз; срок необязательный, ключ можно приостановить, включить или отозвать. Старые `uvm_` не работают. Нет общего правила «90 дней».

Передавай секрет только через безопасное хранилище клиента или переменную окружения `UNIVERUS_API_KEY`. Не помещай его в чат, URL, аргументы команд, репозиторий или логи. Скрипт читает окружение, требует Python 3.10+ и стандартную библиотеку с базой часовых поясов. По умолчанию origin — `https://univerus.ai`; `UNIVERUS_API_BASE_URL` меняй только на доверенный сервер, поскольку туда уйдёт ключ. Для локального теста допускается `http://localhost:<port>`.

Из папки скилла:

```bash
python3 scripts/marketplace.py access
python3 scripts/marketplace.py categories
python3 scripts/marketplace.py orders --today --timezone Europe/Belgrade
python3 scripts/marketplace.py orders --search 'дизайн' --per-page 100 --page 1
python3 scripts/marketplace.py orders --from-at 2026-10-01T00:00:00+02:00 --before-at 2026-10-08T00:00:00+02:00 --date-field discovered
python3 scripts/marketplace.py order <uuid>
```

HTTP GET: `/api/v1/account/access`, `/api/v1/marketplace/categories`, `/api/v1/marketplace/orders`, `/api/v1/marketplace/orders/{uuid}`. Заголовок `Authorization: Bearer <key>`. Эти маршруты также принимают OAuth access token, которым управляет совместимый клиент; скрипт не реализует OAuth-процедуру.

## Фильтры и ответы

| Поле HTTP / MCP filters | CLI | Ограничения |
| --- | --- | --- |
| category_id | --category-id | UUID из категорий |
| search | --search | 2–120 символов после trim |
| from_at, before_at | --from-at, --before-at | ISO datetime со смещением UTC, начало < конец |
| date_field | --date-field | message (default), discovered |
| sort | --sort | newest (default), oldest |
| page | --page | от 1, default 1 |
| per_page | --per-page | 1–100, default 20 |

Пример MCP: `{"filters":{"search":"дизайн","date_field":"discovered","sort":"newest","page":1,"per_page":20}}`. Для карточки: `{"order_id":"<uuid>"}`. Сверяй фактическую схему инструмента, не передавай поля CLI в MCP. Неизвестные поля отклоняются.

Список: `items`, `total`, `page`, `per_page`, `total_pages`; пустой список сохраняет метаданные. Карточка: `id`, `normalized_text` (полный текст), `summary`, `contact_name`, `contact_url`, `source_url`, `message_date`, `created_at`, `category`. `created_at` соответствует первому сохранению, `message_date` может отсутствовать. Отдельного структурированного бюджета и признака вакансии в этом ответе нет. Чтение не запускает сбор источников и не гарантирует полноту внешних сообщений.

## Отказы

- 401: авторизация недействительна. OAuth — переподключить штатным входом; ключ — проверить срок, паузу, отзыв и настройку в хранилище. Не просить секрет и не заменять его cookie.
- 403: проверить scope и текущий доступ аккаунта к бирже; не обещать, что новый ключ восстановит продуктовый доступ. Ориентироваться на безопасное описание сервера; если причина неясна, не утверждать конкретную причину отказа.
- 404 карточки: объявление не найдено или больше не опубликовано.
- 422: исправить параметры по схеме, не повторять тот же запрос.
- 429: соблюдать `Retry-After`, не запускать цикл частых повторов. Общая квота — 120 запросов/мин на владельца между API/MCP и ключами.
- Сеть/5xx: сообщить о недоступности и неполном охвате; ограниченный повтор допустим, бесконечные повторы — нет. Отсутствие доступа не означает отсутствие заказов.

В MCP проверяй также `isError` и текст отказа: транспортный успех ещё не означает успех инструмента. Скрипт выводит JSON в stdout при успехе, безопасную ошибку в stderr и ненулевой код при отказе; секрет и тело ошибки сервера не печатаются.

Публичная документация выбранного origin: `/docs/api/quickstart.md`, `/docs/api/skill.md`, `/api/v1/openapi.json`. Платформенный skill.md посвящён общему чтению данных и не устанавливает этот помощник автоматически.
