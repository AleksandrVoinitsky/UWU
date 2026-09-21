# REST API

Интерактивная документация доступна по адресу `/api/docs` (Swagger UI) и
`/api/openapi.json` (OpenAPI-схема).

Авторизация: `Authorization: Bearer <token>` (токен из `POST /api/auth/login`).

## Аутентификация

| Метод | Путь | Описание |
| --- | --- | --- |
| POST | `/api/auth/login` | Вход, возвращает `{access_token, token_type}` |

## Пользователи и роли (только администратор)

| Метод | Путь | Описание |
| --- | --- | --- |
| GET | `/api/users` | Список пользователей |
| POST | `/api/users` | Создать пользователя |
| GET | `/api/users/{id}` | Получить пользователя |
| PATCH | `/api/users/{id}` | Обновить пользователя |
| DELETE | `/api/users/{id}` | Удалить пользователя (нельзя админа) |
| GET | `/api/users/roles/list` | Список ролей |
| POST | `/api/users/roles` | Создать роль |
| GET | `/api/users/permissions` | Доступные права |

## Справочники

| Метод | Путь |
| --- | --- |
| GET/POST | `/api/catalog/valyuty` |
| GET/POST | `/api/catalog/stavki_nds` |
| GET/POST | `/api/catalog/edinitsy` |
| GET/POST | `/api/catalog/firmy` |
| GET/POST | `/api/catalog/sklady` |
| GET/POST | `/api/catalog/kassy` |
| GET/POST | `/api/catalog/kontragenty` |
| GET/POST | `/api/catalog/dogovory` |
| GET/POST | `/api/catalog/nomenklatura` |
| GET/POST | `/api/catalog/tipy_tsen` |
| GET | `/api/catalog/constants` |
| PUT | `/api/catalog/constants/{key}` |

## Документы

| Метод | Путь | Описание |
| --- | --- | --- |
| GET | `/api/documents` | Журнал (фильтры: `doc_type`, `start`, `end`, `kontragent_id`) |
| GET | `/api/documents/{id}` | Документ со строками |
| POST | `/api/documents` | Создать документ |
| POST | `/api/documents/{id}/post` | Провести |
| POST | `/api/documents/{id}/unpost` | Отменить проведение |
| DELETE | `/api/documents/{id}` | Пометить на удаление |

## Отчёты

| Метод | Путь | Описание |
| --- | --- | --- |
| GET | `/api/reports/stock/balances` | Остатки товаров |
| GET | `/api/reports/stock/movements` | Движения товаров (`start`, `end`, `nomenklatura_id`) |
| GET | `/api/reports/sales` | Продажи (`start`, `end`) |
| GET | `/api/reports/settlements` | Взаиморасчёты |
| GET | `/api/reports/money/balance` | Остаток денег |
| GET | `/api/reports/money/movements` | Движения денег (`start`, `end`) |

## Пример

```bash
# Вход
curl -X POST http://localhost:8000/api/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"login":"admin","password":"admin"}'

# Остатки товаров
curl http://localhost:8000/api/reports/stock/balances \
  -H 'Authorization: Bearer <token>'
```
