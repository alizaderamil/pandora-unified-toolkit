# Xiaomi 17 Pro China (pandora) — Восстановление

> Полный журнал попыток восстановления заблокированного Xiaomi 17 Pro China
> стуck в Fastboot после повторной блокировки загрузчика.

**Устройство:** Xiaomi 17 Pro China (`25098PN5AC`), кодовое имя `pandora`, чип Snapdragon 8 Elite
**Дата проблемы:** 15 октября 2026
**Статус:** В процессе восстановления

---

## 📱 Текущее состояние

| Параметр | Значение |
|----------|----------|
| Модель | `pandora` (25098PN5AC) |
| Чип | Snapdragon 8 Elite |
| UFS | `SM8 UFS` (Samsung) ✓ |
| Серийник | `d5835558` |
| Загрузчик | **ЗАБЛОКИРОВАН** (`unlocked: no`) |
| Secure | yes |
| Активный слот | `a` |
| Слот A | `unbootable=yes, successful=yes, retry=4` |
| Слот B | `unbootable=yes, successful=no` |
| Anti-rollback | 1 |
| Патч безопасности | 2026-10-01 |
| Батарея | 4384 mV (норма) |
| Причина ошибки | `LoadImageAndAuth Fail` |

**Токен (динамический):**
- `VQEBJQEQGdU6x2Z35UYa30b5ehbdvQMHcGFuZG9yYQIIAAAEasOr5Uk`

**Последняя установленная система:** OS4.0.2.0.XBLCNXM (Android 17, патч 2026-10-01)

---

## 📖 История событий

### До проблемы
1. Разблокировали загрузчик через [UnlockerBL_8EG5_v2](D:/xiaomi/UnlockerBL_8EG5_v2_rus) (linuxloader_unlock.efi/efisp)
2. Установили xiaomi.eu + TWRP antocorvo3000 3.7.1_16
3. Восстановили `recovery_a` и `vbmeta_a` из OS4 OTA
4. Android загружался нормально
5. Google Play показал: "Lock bootloader to fix issue"

### Момент поломки
```
fastboot erase efisp         → OKAY
fastboot oem lock            → OKAY
fastboot reboot              → возврат в Fastboot
```

После этого телефон не может выйти из Fastboot.
Оба слота помечены unbootable, образы не проходят проверку подписи.

---

## 🔍 Что было проверено (ВСЁ отказало)

### Fastboot команды
| Команда | Результат |
|---------|-----------|
| `fastboot oem edl` | ❌ Error Invalid Parameter |
| `fastboot reboot edl` | ❌ unknown reboot target |
| `fastboot reboot emergency` | ❌ unknown reboot target |
| `fastboot oem reboot-edl` | ❌ unknown command |
| `fastboot oem unlock` | ❌ Token Verify Failed |
| `fastboot flashing unlock` | ❌ unknown command |
| `fastboot flashing get_unlock_ability` | ✓ `1` (разрешено) |
| `fastboot set_active a` | ❌ Slot Change not allowed in Lock State |
| `fastboot continue` | ❌ Failed to load image: Load Error |
| `fastboot oem fbreason` | ✓ Reason:LoadImageAndAuth Fail |
| `fastboot oem shouhoujiance` | ✓ 10 МБ дамп логов |
| `fastboot oem device-info` | ✓ Verity mode: true, unlocked: false |

### Полный перебор (90+ команд)
Проверено 48 getvar переменных + 60 OEM-команд.
**Нет скрытых команд, нет обходных путей через fastboot.**

### Официальные инструменты
| Инструмент | Результат |
|-----------|-----------|
| Mi Unlock Tool 7.6.727.43 | ❌ Ошибка **20045** (регион аккаунта ≠ регион телефона) |
| CPTool V1.6.3 Fastboot→EDL | ❌ Your account is unauthorized |
| CPTool V1.4.4 BL Unlock | ❌ Требует патч < Feb 2026 |
| CPTool V1.5.9 Temp Root | ❌ Требует работающий Android 16 |
| Modified MiFlash Pro | ❌ Требует EDL |

### Mi аккаунт
✓ Отвязан через [i.mi.com](https://i.mi.com) → Find Device → Remove this device

---

## 🎯 ОСНОВНЫЕ ПУТИ ВОССТАНОВЛЕНИЯ

### 🥇 Путь 1: Аппаратный EDL + Auth-Free Firehose (новый метод!)

**Открытие от 6 мая 2026:** на DroidWin появился auth-free firehose для SD 8 Elite,
подходит для hard-bricked устройств. Условия:
- UFS должен быть НЕ Toshiba/Kioxia ✓ (у нас Samsung SM8 UFS)
- Патч безопасности от Feb 2026 до Apr 2026 (у нас Oct 2026 — **может не сработать**)
- Устройство должно войти в EDL (9008)

**Шаги:**

1. **Войти в EDL аппаратно:**
   - Выключить телефон (Power 20 сек)
   - Зажать Volume Up + Volume Down одновременно
   - Не отпуская кнопки, подключить USB
   - Проверить Device Manager → должен появиться "Qualcomm HS-USB QDLoader 9008"

2. **Если EDL появился:**
   - Скачать firehose: [DroidWin ссылка](https://droidwin.com/authentication-free-edl-firehose-unbrick-xiaomi-snapdragon-8-elite/)
   - Прошить сначала abl partition
   - Потом engineering ROM
   - Если бутлоадер остался заблокирован — использовать unlock tool от 24 апреля

**Статус:** НЕ пробовали. Рекомендуется первым делом.

---

### 🥈 Путь 2: UMcrew (TeamViewer сервис)

- Telegram: [@UMcrew](https://t.me/UMcrew)
- Схема: удалённое подключение через TeamViewer
- Цена: ~$20-50
- Мануал: https://teletype.in/@umcrew/4ZIljkFcy

**Статус:** Написали 15 октября, ждём ответ.

Готовое сообщение: [umcrew_package/сообщение_umcrew.txt](D:/xiaomi/umcrew_package/сообщение_umcrew.txt)

---

### 🥉 Путь 3: Three Tools GSM (резерв)

- Telegram: [@three_tools_gsm](https://t.me/three_tools_gsm)
- Аналог UMcrew, та же схема
- Мануал: https://teletype.in/@3toolsgsm/edl_xiaomi_en

**Статус:** Запасной вариант если UMcrew откажет.

---

### Путь 4: Mi Unlock с китайским аккаунтом (долго)

1. Купить китайский номер (sms-activate.org, ~$1)
2. Регистрация Mi-аккаунта на китайской версии
3. Привязать телефон по IMEI
4. Ждать **168 часов (7 дней)**
5. Mi Unlock Tool → должен выдать токен
6. После разблокировки восстановить recovery/vbmeta

**Статус:** Не начинали. Долгий но надёжный путь.

---

### Путь 5: UMT Pro Dongle (платный донгл)

- Цена: $60-80
- Поддерживает SD 8 Elite с ноября 2024 (QcFire v13.6+)
- Требует разборку и тестпоинты
- Для самостоятельного восстановления

**Статус:** Крайний вариант.

---

## 📁 Структура папки D:\xiaomi

```
D:\xiaomi\
├── README.md                           # Этот файл
├── pandora_recovery.py                 # GUI утилита диагностики
├── pandora_last_chance.py              # Исчерпывающий перебор команд
├── pandora-ota_full-OS4.0.2.0...zip    # Прошивка OS4 (9 GB)
├── pandora-ota_full-OS3.0.319...zip    # Прошивка OS3 (8.5 GB)
├── pandora_images_OS3...tgz            # Fastboot images (12 GB)
├── xiaomi.eu_PANDORA_OS3...zip         # xiaomi.eu ROM
├── adb\                                # ADB/Fastboot инструменты
├── MiFlash20220507\                    # Mi Flash Tool
├── miflash_pro-en-7.3.706.21\          # MiFlash Pro
├── UnlockerBL_8EG5_v2_rus\             # Инструмент разблокировки (прошлый)
├── BATCH_BL_TO_EDL-6.5.817.32\         # Fastboot→EDL (отказал)
├── recovery_reports\                    # Отчёты диагностики
├── last_chance_reports\                 # Отчёты полного перебора
└── umcrew_package\                      # Пакет для сервиса
    ├── ЧТО_ДЕЛАТЬ.txt
    ├── сообщение_umcrew.txt
    ├── РЕЗЕРВНЫЕ_СЕРВИСЫ.txt
    ├── diagnostic_summary.txt
    └── *.json (диагностические отчёты)
```

---

## 🛠 Утилиты в репозитории

### [pandora_recovery.py](pandora_recovery.py)
GUI инструмент диагностики с кнопками:
- Полная диагностика (все переменные fastboot)
- Попытка EDL (4 метода)
- Список разделов
- Открыть отчёты

### [pandora_last_chance.py](pandora_last_chance.py)
Исчерпывающий перебор:
- 48 getvar переменных
- 60 OEM-команд (документированные + недокументированные)
- Записывает всё в JSON отчёты

### Запуск
```powershell
python D:\xiaomi\pandora_recovery.py
python D:\xiaomi\pandora_last_chance.py
```

---

## ⚠️ ВАЖНО — чего НЕ делать

- ❌ Не прошивать через MiFlash наугад — anti-rollback убьёт телефон
- ❌ Не соглашаться на "бесплатный обход" от незнакомцев
- ❌ Не отдавать телефон в случайный местный сервис
- ❌ Не делать `fastboot flash` без разблокировки
- ❌ Не пробовать Toshiba/Kioxia firehose (у нас Samsung UFS, это нормально)

---

## 📊 Техническая справка

### Chain of trust Qualcomm (почему нельзя взломать «в лоб»)
1. **PBL** — зашит в маске чипа (ROM)
2. PBL проверяет подпись firehose по ключам из **QFPROM** (физические предохранители)
3. ABL проверяет подпись boot/recovery/vbmeta образов
4. VBmeta проверяет подписи остальных разделов

Любой unsigned код отклоняется на уровне ПЗУ. Единственные пути:
- **Валидная подпись Xiaomi** (ключ не публичный)
- **Эксплойт** (GBL exploit, патченный в марте 2026)
- **Fault injection** (аппаратная атака, лаборатория)

### Что такое auth-free firehose
Утечка firehose-загрузчика, подписанного Xiaomi, но без привязки к конкретному
аккаунту. Загрузчик загружается в EDL, принимает команды flash без запроса авторизации
на сервере Xiaomi.

---

## 🔗 Полезные ссылки

- [DroidWin — Auth-Free Firehose SD 8 Elite](https://droidwin.com/authentication-free-edl-firehose-unbrick-xiaomi-snapdragon-8-elite/)
- [DroidWin — EDL Unbrick Skip Auth](https://droidwin.com/edl-unbrick-is-now-available-for-xiaomi-devices-skip-authentication/)
- [GitHub — SD 8 Elite BL Unlock](https://github.com/panks/xiaomi-sd8eg5-bootloader-unlock-relock) (требует патч < Mar 2026)
- [DroidWin — Authentication-Free EDL (Pack 1-4)](https://droidwin.com/edl-unbrick-is-now-available-for-xiaomi-devices-skip-authentication/)
- [UMcrew мануал](https://teletype.in/@umcrew/4ZIljkFcy)
- [Three Tools GSM мануал](https://teletype.in/@3toolsgsm/edl_xiaomi_en)
- [66rom — Xiaomi 17 Pro инструмент v4.3](https://www.66rom.com/thread-46518-1-1.html)
- [CPTool](https://cp-tool.com/)
- [Xiaomi.eu — похожий случай](https://xiaomi.eu/community/threads/help-wtb-unbrick-service-for-xiaomi-17-pro-max-cn-version-edl-9008.76712/)

---

## 📝 Что делать сейчас (приоритет)

1. **ПРЯМО СЕЙЧАС:** Попробовать аппаратный EDL (Vol Up + Vol Down + USB)
2. **Если EDL сработал:** Скачать auth-free firehose с DroidWin
3. **Параллельно:** Ждать ответа [@UMcrew](https://t.me/UMcrew)
4. **Через 24 часа:** Если UMcrew молчит — писать [@three_tools_gsm](https://t.me/three_tools_gsm)
5. **Если ничего не работает:** Начать создавать китайский Mi-аккаунт (неделя ожидания)

---

Создано с помощью Claude Code — AI-ассистент для разработки.
