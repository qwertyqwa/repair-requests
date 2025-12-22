# Учет заявок на ремонт (Flask)

Учебный проект: учет заявок на ремонт бытовой техники.

Документация по **Заданию 1**: `docs/assignment1.md`.

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

Пользователи создаются автоматически при первом запуске и сохраняются в `data/users.json`.
