"""Проверка РМК: продажа через /rmk/sell и печатная форма."""
import httpx

BASE = "http://localhost:8000"
c = httpx.Client(base_url=BASE, timeout=30)

# Вход пользователем (cookie)
r = c.post("/login", data={"login": "user", "password": "user1234"}, follow_redirects=False)
print("login:", r.status_code)

# Получаем номенклатуру из RMK-данных (страница /rmk)
r = c.get("/rmk")
print("rmk page:", r.status_code)

# Смотрим, есть ли номенклатура в БД (через API отчёта остатков)
r = c.get("/api/reports/stock/balances")
balances = r.json()
print("balances:", [(b["nomenklatura_id"], b["nomenklatura"], str(b["quantity"])) for b in balances] if r.status_code == 200 else r.text)

if balances:
    item = balances[0]
    nomen_id = item["nomenklatura_id"]
    qty = min(float(item["quantity"]), 2.0) if item["quantity"] else 1.0
    # Продажа через РМК
    payload = {"sklad_id": item["sklad_id"], "items": [{"nomenklatura_id": nomen_id, "quantity": qty, "price": 150.0}]}
    r = c.post("/rmk/sell", json=payload)
    print("rmk/sell:", r.status_code, r.text)
    if r.status_code == 200:
        doc_id = r.json()["id"]
        r = c.get(f"/documents/{doc_id}/print")
        print("print form:", r.status_code, "| has invoice:", "invoice" in r.text)
