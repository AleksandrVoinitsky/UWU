"""Локальная проверка клиентского сайта и MiniApp: прогоняет все адреса.

Запуск против работающего стека:  python scripts/test_miniapp.py [BASE]

Для проверки MiniApp-входа подпись initData пропускается в режиме разработки —
запустите стек с ``MINIAPP_DEV=true`` (см. docker-compose).
"""
from __future__ import annotations

import sys

import httpx

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
ok = fail = 0


def check(label: str, cond: bool, extra: str = "") -> None:
    global ok, fail
    print(f"[{'PASS' if cond else 'FAIL'}] {label}  {extra}")
    ok += cond
    fail += (not cond)


def main() -> int:
    c = httpx.Client(base_url=BASE, timeout=30, follow_redirects=False)

    check("healthz", c.get("/healthz").status_code == 200)

    # Регистрация покупателя (сайт).
    r = c.post("/shop/api/register", json={"phone": "+70001112233", "password": "secret123", "name": "Локальный"})
    check("register", r.status_code == 201, str(r.status_code))
    if r.status_code != 201:
        # возможно, уже существует — пробуем войти
        r = c.post("/shop/api/login", json={"phone": "+70001112233", "password": "secret123"})
        check("login", r.status_code == 200, str(r.status_code))
    token = r.json().get("access_token", "")
    h = {"Authorization": f"Bearer {token}"}

    check("catalog (API)", c.get("/shop/api/products").status_code == 200)
    check("categories (API)", c.get("/shop/api/categories").status_code == 200)
    check("catalog page", c.get("/shop/").status_code == 200)
    check("register page", c.get("/shop/register").status_code == 200)
    check("login page", c.get("/shop/login").status_code == 200)

    products = c.get("/shop/api/products").json()
    if products:
        pid = products[0]["id"]
        r = c.post("/shop/api/cart", json={"nomenklatura_id": pid, "quantity": 1}, headers=h)
        check("cart add", r.status_code == 201, str(r.status_code))
        check("cart page", c.get("/shop/cart", cookies={"customer_token": token}).status_code == 200)

        r = c.post("/shop/api/checkout", headers=h)
        check("checkout", r.status_code == 201, str(r.status_code))
        oid = r.json().get("id") if r.status_code == 201 else None
        if oid:
            check("order page", c.get(f"/shop/orders/{oid}", cookies={"customer_token": token}).status_code == 200)
            pr = c.get(f"/shop/api/orders/{oid}/pdf", headers=h)
            check("order PDF", pr.status_code == 200 and pr.content[:5] == b"%PDF-", pr.headers.get("content-type", ""))
    else:
        print("  (нет товаров в наличии — пропускаю корзину/заказ)")

    # MiniApp вход (dev-режим: подпись не проверяется).
    r = c.get("/shop/mini", params={"channel": "telegram", "user_id": "999", "name": "MiniUser"})
    check("miniapp entry (redirect)", r.status_code == 303, str(r.status_code))
    mini_cookie = r.cookies.get("customer_token")
    check("miniapp sets cookie", bool(mini_cookie))
    if mini_cookie:
        check("miniapp catalog (after auth)", c.get("/shop/", cookies={"customer_token": mini_cookie}).status_code == 200)

    # Админ: покупатели видны.
    admin_token = c.post("/api/auth/login", json={"login": "admin", "password": "admin"}).json().get("access_token")
    r = c.get("/admin/customers", cookies={"access_token": admin_token})
    check("admin customers page", r.status_code == 200, str(r.status_code))

    print(f"\n=== RESULT: {ok} passed, {fail} failed ===")
    return 1 if fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
