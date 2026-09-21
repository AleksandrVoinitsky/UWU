"""Создаёт учётную запись обычного пользователя (оператора) для торгового интерфейса."""
import httpx

BASE = "http://localhost:8000"
LOGIN = "user"
PASSWORD = "user1234"
FULL_NAME = "Пользователь"

c = httpx.Client(base_url=BASE, timeout=30)

# 1. Вход администратора
r = c.post("/api/auth/login", json={"login": "admin", "password": "admin"})
if r.status_code != 200:
    print("FAIL: не удалось войти администратором:", r.status_code, r.text)
    raise SystemExit(1)
token = r.json()["access_token"]
h = {"Authorization": f"Bearer {token}"}

# 2. Найти роль оператора
r = c.get("/api/users/roles/list", headers=h)
roles = r.json()
op = next((x for x in roles if x["key"] == "operator"), None)
role_id = op["id"] if op else None

# 3. Создать пользователя (или сообщить, что уже есть)
r = c.post("/api/users", headers=h, json={
    "login": LOGIN, "password": PASSWORD, "full_name": FULL_NAME, "role_id": role_id,
})
if r.status_code == 201:
    print(f"OK: создан пользователь login={LOGIN} password={PASSWORD} role=operator")
elif r.status_code == 409:
    print(f"OK: пользователь {LOGIN} уже существует")
else:
    print("FAIL:", r.status_code, r.text)
    raise SystemExit(1)

# 4. Проверка входа нового пользователя
r = c.post("/api/auth/login", json={"login": LOGIN, "password": PASSWORD})
print("Login check:", r.status_code, "(200 = ок)")
