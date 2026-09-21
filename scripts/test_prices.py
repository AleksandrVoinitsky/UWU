"""Проверка управления ценами: закупочная + виды цен с наценкой + свободная цена."""
import httpx

BASE = "http://localhost:8000"
c = httpx.Client(base_url=BASE, timeout=30)

# Вход
c.post("/login", data={"login": "user", "password": "user1234"}, follow_redirects=False)

# 1. Создать тип цен с наценкой 20%
r = c.post("/catalog/tipy_tsen", data={"name": "Оптовая", "markup_percent": "20"}, follow_redirects=False)
print("create tip tsen:", r.status_code)

# 2. Создать номенклатуру с закупочной ценой 100 и свободной 130
r = c.post("/catalog/nomenklatura", data={"name": "Кофе зерновой", "vid": "tovar", "purchase_price": "100", "retail_price": "130"}, follow_redirects=False)
print("create nomenklatura:", r.status_code)

# 3. Проверить, что закупочная/свободная сохранились
r = c.get("/catalog/nomenklatura")
print("nomen page has purchase_price col:", "Закуп." in r.text, "| has Цены btn:", "Цены" in r.text)

# 4. Проверить расчёт автонаценки через сервис (через API отчёта остатков нет; проверим напрямую в БД)
import subprocess
out = subprocess.run(
    ["docker", "exec", "uwu-db-1", "psql", "-U", "uwu", "-d", "uwu", "-t", "-c",
     "SELECT n.name, n.purchase_price, n.retail_price, t.name, t.markup_percent, round(n.purchase_price*(1+t.markup_percent/100),2) FROM nomenklatura n CROSS JOIN tipy_tsen t WHERE n.name='Кофе зерновой'"],
    capture_output=True, text=True,
)
print("DB prices+auto:", out.stdout.strip())
