# Local Development

## Start The App

```powershell
$env:PYTHONPATH="src;."
E:\zjl\CMU\research\website\.venv\Scripts\python.exe -m uvicorn --app-dir . apps.web.app:app --host 127.0.0.1 --port 8147
```

## Run Tests

```powershell
$env:PYTHONPATH="src;."
E:\zjl\CMU\research\website\.venv\Scripts\python.exe -B -m unittest discover -s tests
```

## Run Repo Guard

```powershell
$env:PYTHONPATH="src;."
E:\zjl\CMU\research\website\.venv\Scripts\python.exe scripts/validate_repo.py
```

## Run Smoke Test

```powershell
$env:PYTHONPATH="src;."
E:\zjl\CMU\research\website\.venv\Scripts\python.exe scripts/smoke_test_app.py
```
