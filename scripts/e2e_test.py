"""Сквозной E2E-тест работающего Docker-стека (http://127.0.0.1:8000).

Проверяет полный торговый цикл через REST API. Сравнивает значения как числа
(JSON сериализует Decimal в float), включая UTF-8 round-trip кириллицы.
"""
from __future__ import annotations

import sys

import httpx

BASE = "http://127.0.0.1:8000"
ok = 0
fail = 0


def check(label: str, cond: bool, extra: str = "") -> None:
    global ok, fail
    mark = "PASS" if cond else "FAIL"
    print(f"[{mark}] {label}  {extra}")
    if cond:
        ok += 1
    else:
        fail += 1


def f(x) -> float:
    return float(x)


def main() -> int:
    c = httpx.Client(base_url=BASE, timeout=30)

    # 1. Вход администратора
    r = c.post("/api/auth/login", json={"login": "admin", "password": "admin"})
    check("login admin", r.status_code == 200)
    token = r.json()["access_token"]
    h = {"Authorization": f"Bearer {token}"}

    # 2. Справочники (кириллица!)
    r = c.post("/api/catalog/sklady", headers=h, json={"code": "001", "name": "Основной склад", "tip": "optovy"})
    sklad = r.json() if r.status_code == 201 else None
    check("create sklad (UTF-8 name)", sklad is not None and sklad["name"] == "Основной склад",
          repr(sklad and sklad["name"]))

    r = c.post("/api/catalog/nomenklatura", headers=h, json={"code": "", "name": "Телевизор Samsung", "vid": "tovar"})
    n1 = r.json()
    check("create nomenklatura #1", r.status_code == 201 and n1["name"] == "Телевизор Samsung" and n1["code"] == "001")

    r = c.post("/api/catalog/nomenklatura", headers=h, json={"code": "", "name": "Смартфон iPhone", "vid": "tovar"})
    n2 = r.json()
    check("create nomenklatura #2", r.status_code == 201 and n2["code"] == "002")

    r = c.post("/api/catalog/kontragenty", headers=h, json={"code": "", "name": "ООО Покупатель", "inn": "7701234567"})
    kg = r.json()
    check("create kontragent (UTF-8)", r.status_code == 201 and kg["name"] == "ООО Покупатель")

    # 3. Приход (две партии по разным ценам)
    r = c.post("/api/documents", headers=h, json={
        "doc_type": "prihod", "subtype": "credit", "date": "2025-01-01",
        "sklad_id": sklad["id"], "kontragent_id": kg["id"],
        "items": [{"nomenklatura_id": n1["id"], "quantity": 5, "price": 10000}],
    })
    p1 = r.json()
    check("create prihod #1", r.status_code == 201)
    r = c.post(f"/api/documents/{p1['id']}/post", headers=h)
    check("post prihod #1", r.status_code == 200 and r.json()["status"] == "posted")

    r = c.post("/api/documents", headers=h, json={
        "doc_type": "prihod", "subtype": "credit", "date": "2025-01-02",
        "sklad_id": sklad["id"], "kontragent_id": kg["id"],
        "items": [{"nomenklatura_id": n1["id"], "quantity": 5, "price": 12000}],
    })
    p2 = r.json()
    c.post(f"/api/documents/{p2['id']}/post", headers=h)

    # 4. Остатки после прихода (10 единиц, себестоимость 110000)
    r = c.get("/api/reports/stock/balances", headers=h)
    tv = next((b for b in r.json() if b["nomenklatura_id"] == n1["id"]), None)
    check("balance = 10 after 2 prihods", tv is not None and f(tv["quantity"]) == 10.0, str(tv and tv["quantity"]))
    check("cost = 110000", tv is not None and f(tv["cost"]) == 110000.0, str(tv and tv["cost"]))

    # 5. Расход 3 шт (FIFO) + взаиморасчёты
    r = c.post("/api/documents", headers=h, json={
        "doc_type": "rashod", "subtype": "credit", "date": "2025-01-03",
        "sklad_id": sklad["id"], "kontragent_id": kg["id"],
        "items": [{"nomenklatura_id": n1["id"], "quantity": 3, "price": 15000}],
    })
    rashod = r.json()
    r = c.post(f"/api/documents/{rashod['id']}/post", headers=h)
    check("post rashod", r.status_code == 200 and r.json()["status"] == "posted")

    r = c.get("/api/reports/stock/balances", headers=h)
    tv = next((b for b in r.json() if b["nomenklatura_id"] == n1["id"]), None)
    check("balance = 7 after rashod 3", tv is not None and f(tv["quantity"]) == 7.0, str(tv and tv["quantity"]))
    # FIFO: списано 3*10000=30000, остаток себестоимости 2*10000 + 5*12000 = 80000
    check("FIFO cost = 80000 (2*10000+5*12000)", tv is not None and f(tv["cost"]) == 80000.0, str(tv and tv["cost"]))

    # 6. Взаиморасчёты: продажа 45000 (долг нам), приход в кредит 110000 (мы должны)
    r = c.get("/api/reports/settlements", headers=h)
    row = next((x for x in r.json() if x["kontragent_id"] == kg["id"]), None)
    check("settlement debt = -65000", row is not None and f(row["debt"]) == -65000.0, str(row and row["debt"]))

    # 7. Контроль остатков: расход сверх остатка -> 409
    r = c.post("/api/documents", headers=h, json={
        "doc_type": "rashod", "subtype": "cash", "date": "2025-01-04",
        "sklad_id": sklad["id"],
        "items": [{"nomenklatura_id": n1["id"], "quantity": 999, "price": 100}],
    })
    over = r.json()
    r = c.post(f"/api/documents/{over['id']}/post", headers=h)
    check("restock control blocks oversell (409)", r.status_code == 409)

    # 8. Перемещение 2 шт
    r = c.post("/api/catalog/sklady", headers=h, json={"code": "002", "name": "Розничный склад", "tip": "roznichny"})
    sklad2 = r.json()
    r = c.post("/api/documents", headers=h, json={
        "doc_type": "peremeshenie", "date": "2025-01-05",
        "sklad_id": sklad["id"], "sklad_to_id": sklad2["id"],
        "items": [{"nomenklatura_id": n1["id"], "quantity": 2, "price": 10000}],
    })
    move = r.json()
    r = c.post(f"/api/documents/{move['id']}/post", headers=h)
    check("post peremeshenie", r.status_code == 200)
    r = c.get("/api/reports/stock/balances", headers=h)
    bal = r.json()
    src = next((b for b in bal if b["nomenklatura_id"] == n1["id"] and b["sklad_id"] == sklad["id"]), None)
    dst = next((b for b in bal if b["nomenklatura_id"] == n1["id"] and b["sklad_id"] == sklad2["id"]), None)
    check("transfer: src=5 dst=2",
          src and f(src["quantity"]) == 5.0 and dst and f(dst["quantity"]) == 2.0,
          f"src={src and src['quantity']} dst={dst and dst['quantity']}")

    # 9. Деньги: ПКО 5000
    r = c.post("/api/documents", headers=h, json={
        "doc_type": "pko", "date": "2025-01-06", "kontragent_id": kg["id"], "total": 5000,
    })
    pko = r.json()
    r = c.post(f"/api/documents/{pko['id']}/post", headers=h)
    check("post pko", r.status_code == 200)
    r = c.get("/api/reports/money/balance", headers=h)
    check("money balance = 5000", f(r.json()["balance"]) == 5000.0, r.json()["balance"])

    # 10. Админ: пользователи и роли
    r = c.get("/api/users", headers=h)
    check("list users (admin email serializes)", r.status_code == 200, f"{r.status_code}")
    if r.status_code == 200:
        admin = next((u for u in r.json() if u["is_admin"]), None)
        check("admin user present", admin is not None and admin["login"] == "admin")

    r = c.post("/api/users", headers=h, json={"login": "oper", "password": "pass1234", "full_name": "Оператор"})
    check("create user", r.status_code == 201)
    r = c.get("/api/users/permissions", headers=h)
    check("list permissions", r.status_code == 200, f"{len(r.json()) if r.status_code == 200 else 0} perms")

    # 11. Новая учётная запись входит
    r = c.post("/api/auth/login", json={"login": "oper", "password": "pass1234"})
    check("login operator", r.status_code == 200)

    print(f"\n=== RESULT: {ok} passed, {fail} failed ===")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
