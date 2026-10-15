# Как загрузить в GitHub

Локальный git репозиторий уже создан в `D:\xiaomi\`. Осталось отправить его на GitHub.

## Шаг 1 — Создай репозиторий на GitHub

1. Открой [github.com/new](https://github.com/new) (войди в аккаунт `alizaderamil`)
2. **Repository name:** `xiaomi-pandora-recovery`
3. **Description:** `Xiaomi 17 Pro China (pandora) bootloader lock recovery journal`
4. **Private** ✓ (так как содержит серийник телефона)
5. **НЕ ставь** галочки на README/gitignore/license (у нас всё уже есть)
6. Нажми **Create repository**

## Шаг 2 — Push на GitHub

После создания скопируй и запусти в PowerShell (из D:\xiaomi):

```powershell
cd D:\xiaomi
git remote add origin https://github.com/alizaderamil/xiaomi-pandora-recovery.git
git push -u origin main
```

При первом push GitHub откроет окно браузера для авторизации — просто подтверди.

## Шаг 3 — Проверь

Открой https://github.com/alizaderamil/xiaomi-pandora-recovery
Должен быть виден README с полной историей и файлы.

## С другого ПК (как попасть)

```powershell
# Установи git если нет
# Клонируй репозиторий
git clone https://github.com/alizaderamil/xiaomi-pandora-recovery.git
cd xiaomi-pandora-recovery
```

Все утилиты, отчёты, инструкции будут доступны.

## Обновление репозитория

Когда что-то поменяется (новые отчёты, новая попытка):

```powershell
cd D:\xiaomi
git add .
git commit -m "описание изменений"
git push
```

## Что НЕ в git

Крупные файлы прошивок (zip, tgz) не включены — их всегда можно скачать заново:
- [miuirom.net/model/pandora.ttt](https://mifirm.net/model/pandora.ttt)
- [miuirom.org/phones/xiaomi-17-pro](https://miuirom.org/phones/xiaomi-17-pro)

Также не включены папки с инструментами (adb, MiFlash, UnlockerBL) — скачиваются отдельно.
