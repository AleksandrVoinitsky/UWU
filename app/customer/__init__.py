"""Клиентский сайт/каталог покупателя (отдельная ветвь процесса).

Переиспользует ядро (модели, сервисы, БД), но имеет собственную аутентификацию
(``Customer``) и интерфейс. Логика вынесена в REST API (:mod:`app.customer.api`)
для переиспользования в MiniApp Telegram/MAX.

См. также: :mod:`app.customer.api`, :mod:`app.customer.web`,
:mod:`app.services.customer_service`.
"""
from app.customer.app import create_customer_app

__all__ = ["create_customer_app"]
