# Development convenience Makefile (Windows-friendly via the `dev.ps1` script)

.PHONY: dev db backend frontend test stop

dev: db backend frontend
	@echo "Development environment started. Frontend -> http://localhost:5173/"

db:
	docker compose up -d

backend:
	@powershell -ExecutionPolicy Bypass -File scripts\dev.ps1 -OnlyBackend

frontend:
	@powershell -ExecutionPolicy Bypass -File scripts\dev.ps1 -OnlyFrontend

test:
	.venv\Scripts\python.exe -m pytest -q

stop:
	docker compose down
