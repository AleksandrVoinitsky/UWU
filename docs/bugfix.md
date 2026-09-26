# Журнал исправления багов (Bug Fix)

Сессия классического багфикса. Код изучен (4 параллельных ревизии: сервисы,
web/api/schemas, customer/bots, шаблоны), найденные дефекты исправлены и
покрыты регрессионными тестами.

## Сводка

| ID | Статус | Серьёзность | Место | Описание |
|----|--------|-------------|-------|----------|
| BUG-01 | ✅ исправлен | High (500) | `app/templates/trade/invoice.html`, `app/web/trade.py` | `float - Decimal` при расчёте сдачи |
| BUG-02 | ✅ исправлен | High (MiniApp не работает) | `app/services/miniapp_service.py` | Неверная проверка подписи Telegram initData |
| BUG-03 | ✅ исправлен | High (404 после действий) | `app/customer/web.py` | Редиректы теряют префикс `/shop` |
| BUG-04 | ✅ исправлен | High (500 при входе) | `app/models/customer.py`, миграция | `Customer.phone` VARCHAR(20) переполняется синтетическим телефоном |
| BUG-05 | ✅ исправлен | Medium (500) | `app/services/customer_service.py` | `register` без ограничения длины телефона |
| BUG-06 | ✅ исправлен | Medium (неверные отчёты) | `app/services/cash_service.py` | X/Z-отчёт без фильтра по кассе и границе смены |
| BUG-07 | ✅ исправлен | High (IntegrityError) | `app/services/catalog_service.py` | Строковый `max(code)` застревает на «1000» |
| BUG-08 | ✅ исправлен | Low (дубли номеров) | `app/services/document_service.py` | Коллизии 2-символьных префиксов номеров |
| BUG-09 | ✅ исправлен | Medium (неверный отчёт) | `app/services/report_service.py` | «Долг комитентам» включает долги поставщикам |
| BUG-10 | ✅ исправлен | Medium (ZeroDivision) | `app/services/stock_service.py` | Деление на ноль в методе AVERAGE при qty=0 |
| BUG-11 | ✅ исправлен | High (500 на всех страницах) | `app/templates/base.html`, `app/web/admin.py` | `user.login[0]` при пустом логине + дубль логина |
| BUG-12 | ✅ исправлен | Medium (500) | `app/web/trade.py` | `Decimal()`/`int()` от невалидного ввода (≈30 мест) |
| BUG-13 | ✅ исправлен | Medium (500) | `app/web/trade.py` | Невалидный `DocType`/`DocSubtype`/дата документа |
| BUG-14 | ✅ исправлен | Medium (500) | `app/web/trade.py` | `rmk_sell` не валидирует JSON |
| BUG-15 | ✅ исправлен | Medium (500) | `app/web/trade.py` | `date.fromisoformat()` от query-параметров |
| BUG-16 | ✅ исправлен | Security | `app/web/trade.py` | Отсутствие проверки прав в `zakaz_*` |
| BUG-17 | ✅ исправлен | Security (low) | `app/web/auth.py` | Открытый редирект в `set_language` |

## Детали

### BUG-01 — TypeError «float - Decimal» при печати накладной
- **Симптом:** `/documents/{id}/print` для наличной продажи падает с 500.
- **Причина:** `document.total` — `Decimal`, `document.extra["received"]` — `float` (из JSON), в шаблоне `received - total`.
- **Исправление:** расчёт сдачи вынесен в `document_print` и выполняется в `Decimal` (`Decimal(str(received)) - total`).
- **Тест:** `tests/test_documents.py::test_invoice_print_change_no_type_error`.

### BUG-02 — Неверная проверка подписи Telegram initData
- **Симптом:** любой реальный вход через Telegram MiniApp отклоняется (401).
- **Причина:** `parse_qs` URL-декодирует значения до пересчёта HMAC; подпись считается по сырым (encoded) парам.
- **Исправление:** подпись по `raw`-парам, `user` декодируется отдельно. `make_test_init_data` тоже подписывает по encoded-значениям.
- **Тест:** `tests/test_miniapp.py` (roundtrip по-прежнему зелёный, теперь корректный алгоритм).

### BUG-03 — Редиректы в customer/web.py теряют `/shop`
- **Причина:** приложение смонтировано как `/shop`, но редиректы вели на `/`, `/cart`, `/orders/N`.
- **Исправление:** все редиректы используют `SHOP_PREFIX`.

### BUG-04 — Переполнение `Customer.phone`
- **Причина:** синтетический `ma_telegram_<user_id>` (21+ симв.) не влезал в `VARCHAR(20)`.
- **Исправление:** колонка расширена до `String(64)` + миграция `d4e5f6a7b8c9`.
- **Тест:** `tests/test_bugfix.py::test_find_or_create_customer_long_external_id`.

### BUG-05 — `register` без ограничения длины телефона
- **Исправление:** проверка `len(phone) > 64` → `CustomerError`.
- **Тест:** `tests/test_bugfix.py::test_register_phone_too_long`.

### BUG-06 — X/Z-отчёт без фильтра по кассе
- **Исправление:** `_shift_window` учитывает `kassa_id` и границу `closed_at`.

### BUG-07 — `next_code` застревает на «1000»
- **Причина:** `func.max(model.code)` берёт строковый максимум («999» > «1000»).
- **Исправление:** числовой максимум `func.max(cast(code, Integer))` только среди чисто числовых кодов (`code ~ '^\d+$'`); пустые/нечисловые коды игнорируются.
- **Тест:** `tests/test_bugfix.py::test_next_code_crosses_999`.

### BUG-08 — Коллизии префиксов номеров документов
- **Причина:** `doc_type.value[:2]` — «PE» (PEREOCENKA/PEREMESHENIE), «VV» (VVOD_OSTATKOV/VVOD_OSTATKOV_DENEG).
- **Исправление:** полный `doc_type.value.upper()`.
- **Тесты:** `tests/test_bugfix.py::test_document_number_prefix_no_collision`; обновлён `test_numbering.py`.

### BUG-09 — «Долг комитентам» включает долги поставщикам
- **Исправление:** фильтр по `Document.doc_type == PRIHOD` и `subtype == "realization"`.

### BUG-10 — Деление на ноль в AVERAGE
- **Исправление:** ранний возврат при `total_available == 0`.
- **Тест:** `tests/test_bugfix.py::test_consume_average_zero_quantity`.

### BUG-11 — Пустой/дублирующийся логин пользователя
- **Симптом:** `user.login[0]` в `base.html` → IndexError (500) на всех страницах; дубль логина → IntegrityError.
- **Исправление:** шаблон использует `(user.login or '?')[0]`; `admin_create_user` валидирует пустоту и дубль.
- **Тесты:** `tests/test_bugfix.py::test_admin_create_duplicate_login_no_500`, `test_admin_create_empty_login_no_500`.

### BUG-12 — `Decimal()`/`int()` от невалидного ввода
- **Исправление:** добавлены безопасные `_to_int()` и `_or_decimal()` (ловят `ValueError`/`InvalidOperation`/`TypeError`), заменены ~30 вызовов в формах/query.

### BUG-13 — Невалидный `DocType`/`DocSubtype`/дата документа
- **Исправление:** в `document_create_submit` добавлен `except (ValueError, InvalidOperation)`.

### BUG-14 — `rmk_sell` не валидирует JSON
- **Исправление:** строки разбираются заранее с возвратом 400 при невалидных данных.
- **Тест:** `tests/test_bugfix.py::test_rmk_sell_invalid_item_returns_400`.

### BUG-15 — `date.fromisoformat()` от query-параметров
- **Исправление:** helper `_safe_report_range` (фолбэк на текущий месяц) + try/except в журнале и `zakaz_create`.

### BUG-16 — Отсутствие проверки прав в `zakaz_*`
- **Исправление:** `_deny(user, "documents.write")` в `zakaz_state`/`zakaz_reserve`/`zakaz_ship`.

### BUG-17 — Открытый редирект в `set_language`
- **Исправление:** разрешены только относительные пути (запрещены `//` и внешние схемы).
