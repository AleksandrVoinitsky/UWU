"""Проверка загрузки изображения товара."""
import base64
import httpx

BASE = "http://localhost:8000"
c = httpx.Client(base_url=BASE, timeout=30, follow_redirects=False)

# 1x1 прозрачный PNG.
png = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
)

c.post("/login", data={"login": "user", "password": "user1234"})

# Загружаем фото на товар 1.
files = {"file": ("test.png", png, "image/png")}
r = c.post("/catalog/nomenklatura/1/image", files=files)
print("upload:", r.status_code, r.headers.get("location", ""))

# Проверяем, что изображение отдаётся.
r = c.get("/catalog/nomenklatura")
import re
m = re.search(r'src="/uploads/([^"]+)"', r.text)
print("thumbnail in list:", bool(m), m.group(1) if m else "")
if m:
    r2 = c.get("/uploads/" + m.group(1))
    print("served image:", r2.status_code, r2.headers.get("content-type"))
