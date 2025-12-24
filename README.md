# Учет заявок на ремонт (Flask)

Учебный проект: учет заявок на ремонт бытовой техники.

Документация:
- **Задание 1 (спецификация/алгоритмы):** `docs/assignment1.md`
- **Задание 1 (схемы Mermaid):** `docs/task1.md`
- **Задание 2 (ERD):** `docs/erd.md`
- **Задание 2 (запросы/импорт/бэкап):** `docs/task2_howto.md`
- **Задание 3 (предложения):** `docs/task3_modification_proposals.txt`
- **Задание 3 (качество кода):** `docs/task3_code_quality.md`
- **Задание 3 (РСП):** `docs/Руководство системного программиста XX.md`

## Запуск

### Windows (PowerShell)

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m repair_requests
```

### Linux / WSL / macOS (bash)

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m repair_requests
```

Откройте: http://127.0.0.1:5000

## Пользователи по умолчанию

- `admin` / `admin` (роль: администратор)
- `operator` / `operator` (роль: оператор)
- `master` / `master` (роль: мастер)
- `manager` / `manager` (роль: менеджер по качеству)

Пользователи создаются автоматически при первом запуске и сохраняются в SQLite БД `data/app.db`.

## Тесты

```bash
python -m pytest -q
```

## Отчет (docx)

Инструкции: `report/README.md`.
