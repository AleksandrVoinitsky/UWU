# Дизайн-система и компоненты интерфейса

> Цель — единый визуальный язык «Aurora» (тёмный, стеклянный): глубокий
> тёмно-синий фон с анимированными градиентными пятнами, панели из матового
> стекла, градиентный акцент (синий → бирюзовый), пилюльные чипы/кнопки/табы,
> плавные анимации и переиспользуемые компоненты без дублирования разметки.
> Тёмная тема — по умолчанию.

## Слои

| Слой | Файл | Роль |
| --- | --- | --- |
| Токены и базовые стили | [`app/static/css/style.css`](../app/static/css/style.css) | CSS-переменные, сброс, типографика, все компоненты |
| Иконки | [`app/web/icons.py`](../app/web/icons.py) | данные (словарь `ICONS`) + рендер `icon()` |
| Макросы | [`app/templates/_components.html`](../app/templates/_components.html) | переиспользуемые Jinja-компоненты |
| Клиентская логика | [`app/static/js/app.js`](../app/static/js/app.js) | тема, модальные окна, счётчики, чат, РМК |
| Клиентский сайт | [`app/static/css/customer.css`](../app/static/css/customer.css) | надстройка над `style.css` для магазина `/shop` |

## Токены (CSS-переменные)

Все значения заданы в `:root` (тёмная тема «Aurora» — по умолчанию) и
переопределяются в `[data-theme="light"]` для светлой темы. Ключевые токены:

| Токен | Назначение |
| --- | --- |
| `--bg`, `--bg-soft`, `--surface`, `--surface-2`, `--surface-hover` | фоны/поверхности (тёмно-синие, стеклянные) |
| `--text`, `--text-secondary`, `--text-tertiary` | текст |
| `--border`, `--border-strong` | границы |
| `--accent`, `--accent-2`, `--accent-3`, `--accent-text`, `--accent-soft`, `--accent-ring`, `--accent-grad` | акцент (градиент синий → бирюзовый) |
| `--blue … --gray` | системная палитра (для графиков) |
| `--ok/--warn/--bad` + `-bg` | статусные тона |
| `--glass-bg`, `--glass-blur`, `--glass-border` | «матовое стекло» |
| `--radius-sm … --radius-xl` | скругления |
| `--shadow`, `--shadow-md`, `--shadow-lg` | тени (глубокие, тёмные) |
| `--font`, `--font-mono` | шрифты (системные + моноширинный для чисел) |
| `--ease`, `--ease-spring`, `--dur-*` | кривые и длительности анимаций |

Правило: в шаблонах не задавать «магических» цветов — только через токены, чтобы
смена темы работала автоматически.

## Тема (тёмная по умолчанию)

- **Тёмная тема — базовая** (`:root`): глубокий фон `#070b16`, стеклянные панели,
  градиентный акцент. Светлая тема — вторичная (`[data-theme="light"]`).
- Фон «аврора»: фиксированный слой `.aurora` с тремя размытыми градиентными
  пятнами (синий/бирюзовый/фиолетовый), медленно дрейфующими
  (`@keyframes drift`). Присутствует на всех страницах.
- Ранняя установка в `<head>` каждого шаблона (см.
  [`base.html`](../app/templates/base.html), `login.html`,
  [`customer/base.html`](../app/templates/customer/base.html)) читает
  `localStorage['uwu-theme']` и ставит `data-theme` до отрисовки — без «мигания».
- Переключатель `#theme-toggle` (солнце/луна) в верхней панели; значение
  сохраняется. Без явного выбора — тёмная тема.
- При смене темы меняются только переменные; разметка не меняется.

## Анимации, размытие и фон

- Кривая `--ease` = `cubic-bezier(0.22, 1, 0.36, 1)` (плавное «прибытие»),
  `--ease-spring` — лёгкий «отскок» для модалок и FAB.
- «Матовое стекло»: `.sidebar`, `.topbar`, `.card`, `.kpi-card`, `.login-card`
  используют `backdrop-filter` (размытие). Модальные подложки — размытие фона.
- Фон «аврора» (`.aurora`) дрейфует и отключается при `prefers-reduced-motion`.
- Все анимации уважают `prefers-reduced-motion: reduce` (отключаются).
- Появление контента страницы — класс `.page-enter` (плавное появление).
- Спарклайны (`.sparkline[data-values]`) рисуются на лету инлайн-SVG в
  [`app.js`](../app/static/js/app.js) (`renderSparklines`).

## Иконки

Иконки — инлайн SVG в стиле SF Symbols (обводка, `currentColor`), заданы
декларативно в `ICONS` и рендерятся `icon(name, size, cls)`. Регистрируются как
Jinja-глобал, поэтому в шаблонах достаточно `{{ icon('search', 15) }}`.

- Имя не найдено → пустая строка (мягкая деградация, без исключений).
- Наследуют цвет (`stroke="currentColor"`), так что реагируют на тему.
- Добавление иконки = добавление записи в `ICONS` — без правки шаблонов.

## Макросы (переиспользуемые компоненты)

Шаблоны импортируют макросы с `with context`, чтобы были доступны `lang`, `t`,
`icon`:

```jinja
{% from "_components.html" import search_input, modal, modal_footer, modal_end, empty_row, badge with context %}
```

| Макрос | Сигнатура | Назначение |
| --- | --- | --- |
| `search_input` | `(target, placeholder=None)` | поле поиска, фильтрующее `<table id="target">` |
| `badge` | `(kind, text)` | статусный бейдж (`posted/draft/deleted/neutral/order/blue/purple/orange`) |
| `empty_row` | `(colspan, message=None)` | строка «нет записей» в таблице |
| `empty_state` | `(icon_name, title, hint)` | пустое состояние вне таблицы |
| `modal` | `(id, title)` | открывает `.modal-backdrop` + `.modal` + шапку с кнопкой закрытия |
| `modal_footer` | `(cancel_label=None, submit_label=None)` | подвал модалки (отмена + сохранение) |
| `modal_end` | `()` | закрывает `.modal` и `.modal-backdrop` |
| `field` | `(label, hint=None)` + `caller()` | поле формы с подписью |

Пример каркаса модального окна через макросы:

```jinja
{{ modal('modal-demo', t('common.create', lang) ~ ' · Демо') }}
  <form method="post" action="/demo">
    <div class="modal-body">
      {% call field(t('common.name', lang)) %}<input type="text" name="name" required>{% endcall %}
    </div>
    {{ modal_footer(submit_label=t('common.add', lang)) }}
  </form>
{{ modal_end() }}
```

Макросы устраняют дублирование: каркас карточки/поиска/модалки вынесен в одно
место, шаблоны справочников (`catalog/*`, `dogovory`, `scheta`, `sotrudniki`,
`categories`) содержат только данные и специфичные поля.

## Дашборды

- Торговый: [`trade/dashboard.html`](../app/templates/trade/dashboard.html) —
  «герой»-блок (главный показатель + спарклайн тренда + селектор периода + быстрые
  действия), KPI-карточки с иконками и спарклайнами, графики Chart.js (цвета
  читаются из токенов темы), лента последних продаж, низкие остатки, рекомендации
  к заказу. См. [dashboard](dashboard.md).
- Админ: [`admin/dashboard.html`](../app/templates/admin/dashboard.html) — KPI
  (пользователи/активные/админы/роли), быстрые действия, таблицы пользователей и
  ролей.

## Интернационализация

Новые строки интерфейса — в [`app/translations/ru.json`](../app/translations/ru.json)
и [`app/translations/en.json`](../app/translations/en.json) (ключи `common.theme`,
`common.close`, `common.empty`, `admin.*`). См. [i18n](i18n.md).

## Тесты

[`tests/test_frontend.py`](../tests/test_frontend.py) покрывает: рендер иконок,
наличие тёмной темы и токенов, использование макросов на страницах каталогов,
переработанные дашборды, загрузку `app.js`/`style.css`. См. [testing](testing.md).

## Как расширять

1. Новый визуальный компонент → добавь макрос в `_components.html` и, при
   необходимости, стили в `style.css` (только через токены).
2. Новая иконка → добавь запись в `ICONS` (не дублируй SVG в шаблонах).
3. Новый текст → ключ в обоих JSON-файлах переводов.
4. Оформление — только токенами; явные цвета запрещены (иначе сломается тёмная тема).
