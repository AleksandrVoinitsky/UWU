"""Вставляет проверку прав catalog.write в create/update-маршруты."""
import re

PATH = "app/web/trade.py"
with open(PATH, encoding="utf-8") as fh:
    src = fh.read()

lines = src.split("\n")
out = []
i = 0
CHECK = ['    denied = _deny(user, "catalog.write")', "    if denied:", "        return denied"]

while i < len(lines):
    line = lines[i]
    out.append(line)
    m = re.match(r"async def (create_\w+|update_\w+|dogovor_create|zakaz_create)\(", line)
    if m:
        # Ищем закрывающую строку '):'
        j = i + 1
        while j < len(lines) and lines[j].strip() != "):":
            j += 1
            if j - i > 20:
                j = i
                break
        if lines[j].strip() == "):":
            # Пропускаем всё до '):' включительно, затем вставляем проверку.
            out.extend(lines[i + 1 : j + 1])
            if lines[j + 1].strip().startswith("denied = _deny("):
                pass  # уже вставлено
            else:
                out.extend(CHECK)
            i = j
    i += 1

with open(PATH, "w", encoding="utf-8") as fh:
    fh.write("\n".join(out))
print("done")
