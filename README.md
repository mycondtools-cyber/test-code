# Motor Nameplate Intake Bot

Telegram-бот для прийомки двигунів у ремонт. Приймає фото шильдіка,
розпізнає поля через Claude Vision API і генерує заповнений PDF бланка
підприємства ZURITT (`BON DE TRAVAIL`) на основі векторного шаблону.

## Як працює

1. Користувач у Telegram надсилає фото шильдіка двигуна.
2. Бот викликає Claude Vision (`claude-opus-4-7`) з примусовим
   `tool_use`, який повертає структурований JSON по кожному полю плюс
   список нечитких/пошкоджених полів.
3. Бот показує, що зчитав, і допитується по неякісних та супровідних
   полях (CLIENT, REQ, PO, дата, тип робіт, тощо) по одному.
4. ReportLab малює бланк (`pdf_form.py`) — векторно, точно в стилі
   оригінального бланка ZURITT — і вписує всі зібрані дані.
5. Бот відправляє готовий PDF користувачу.

## Запуск

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # вписати ANTHROPIC_API_KEY та TELEGRAM_BOT_TOKEN
python bot.py
```

## Файли

| Файл | Призначення |
|---|---|
| `vision.py` | Claude Vision wrapper. Один публічний виклик `extract_nameplate(path)`. |
| `pdf_form.py` | ReportLab-генератор бланка. Запуск напряму генерує `out/sample.pdf` для перевірки верстки. |
| `bot.py` | Telegram-бот (python-telegram-bot 21). |

## Перевірка PDF без Telegram

```bash
python pdf_form.py        # створить out/sample.pdf з тестовими даними з шильдіка WEG HGF
```

## Перевірка vision без Telegram

```bash
python vision.py path/to/nameplate.jpg
```

## Поля які питаються вручну

Зчитуються з шильдіка: `marque, hp, rpm, volts, hz, phase, amps, frame,
model, serial, type, enclosure`.

Завжди запитуються в операторa (їх немає на шильдіку):
`bon_de_travail, date_j/m/a, client, req, po, tag, spec, special,
autorise_par, exigence, work_types`.

Якщо vision не зміг прочитати якесь з полів шильдіка — бот спершу
питає його з вказанням причини (відблиск, подряпина, тощо).
