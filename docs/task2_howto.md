# Задание 2 — БД, импорт, бэкап, отчеты

## База данных

- Схема SQLite: `repair_requests/schema.sql`
- ERD (Mermaid): `docs/erd.md`
- Файл БД по умолчанию: `data/app.db`

## Импорт данных (файлы с пометкой import)

В репозиторий добавлен скрипт-импортёр из CSV:

```bash
python scripts/import_tickets_csv.py --csv path/to/tickets.csv
```

Формат CSV (заголовки колонок):
- `appliance_type`
- `appliance_model`
- `issue_type` (опционально)
- `problem_description`
- `client_name`
- `client_phone`
- `status` (`new`/`in_progress`/`awaiting_parts`/`ready`, опционально)
- `assigned_master_username` (опционально)
- `due_at` (ISO datetime, опционально)

## Запросы к БД

Примеры запросов для отчетов: `docs/task2_queries.sql`.

## Резервное копирование

Скрипт бэкапа SQLite:

```bash
python scripts/backup_db.py --db data/app.db --out backups --sql
```

Сохранит:
- копию файла БД (`.db`);
- дамп в `.sql` (опционально, флаг `--sql`).

## Принцип регистрации и доступы

- Саморегистрация отключена.
- Учетные записи создаёт администратор в разделе **Пользователи**.
- Доступ ограничен по ролям (admin/operator/master/manager).

