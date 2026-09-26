# Безопасность

## Аутентификация

- **Единый экран входа** — логин/пароль (веб: `/login`, API: `POST /api/auth/login`).
- **Пароли** — bcrypt (`app/core/security.py`), соль встроена в хеш.
- **Токены** — JWT (HS256), срок жизни `ACCESS_TOKEN_EXPIRE_MINUTES` (по умолчанию
  480 минут). Веб-интерфейс хранит токен в HttpOnly-cookie `access_token`.

## Роли и права

Модель — `app/models/users.py`. Права — строковые ключи (`PERMISSIONS`):

| Ключ | Назначение |
| --- | --- |
| `users.manage` | Управление пользователями и правами |
| `catalog.read` / `catalog.write` | Справочники |
| `documents.read` / `documents.write` / `documents.post` | Документы |
| `reports.read` | Отчёты |
| `service.settings` | Константы/настройки |

Встроенные роли (`RoleKey`): `admin`, `operator`, `accountant`. Администратор
(`User.is_admin`) имеет все права независимо от роли.

### Разделение интерфейсов

- **Администратор** (`is_admin=True`) — не видит торговый интерфейс, только
  управление пользователями/ролями, настройки и документацию.
- **Оператор/бухгалтер** — торговый интерфейс (справочники, документы, отчёты).

Проверка прав: `User.has_permission(key)`; для API — `require_admin()` и
`get_current_user()` в `app/core/deps.py`.

## Рекомендации по развёртыванию

- Задать сильный `SECRET_KEY` и `ADMIN_PASSWORD` через переменные окружения.
- Служба не отдаёт хеши паролей наружу (схема `UserOut` исключает `password_hash`).
- Cookie `access_token` имеет флаги `httponly`, `samesite=lax` и `secure`
  (в `ENVIRONMENT=production`).

## Защиты, реализованные в сервисе

- **Rate limiting** (`app/core/ratelimit.py`) — лимит попыток входа (10 за 60 с
  по ключу IP + логин) на `/api/auth/login` и веб-входе; превышение → 429.
- **CSRF-защита** (`app/main.py`, middleware) — для state-changing запросов
  проверяется same-origin (`Origin`/`Referer` против `Host`); cross-site → 403.
- **Fail-fast секретов** (`app/core/security.py`) — при `ENVIRONMENT=production`
  небезопасный `SECRET_KEY`/`ADMIN_PASSWORD`/включённый `MINIAPP_DEV` блокируют
  запуск (`RuntimeError`).
- **Проверка свежести initData** (`app/services/miniapp_service.py`) — подпись
  MiniApp принимается только при `auth_date`/`vk_ts` в пределах 24 часов.
- **Экранирование JSON в `<script>`** — пользовательские данные в шаблонах
  сериализуются через `_json_safe` (защита от stored XSS).
- **Проверка прав** — применяется и на REST API, и на веб-слое
  (`_require_web_read` в `app/web/trade.py`).
