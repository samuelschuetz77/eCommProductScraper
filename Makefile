# Development convenience Makefile (Windows-friendly via the `dev.ps1` script)

.PHONY: dev db backend frontend test stop

dev: db backend frontend
	@echo "Development environment started. Frontend -> http://localhost:5173/"

db:
	docker compose up -d

backend:
	@powershell -ExecutionPolicy Bypass -File scripts\dev.ps1 -OnlyBackend

frontend:
	@powershell -NoProfile -ExecutionPolicy Bypass -Command "Try { Start-Process -FilePath 'powershell' -ArgumentList '-NoProfile -ExecutionPolicy Bypass -Command \"cd \"' + (Resolve-Path frontend).Path + ' ; npm run dev\"' -WorkingDirectory (Resolve-Path frontend).Path -WindowStyle Normal -ErrorAction Stop } Catch { Write-Host 'fallback: running npm --prefix frontend run dev (foreground)'; npm --prefix frontend run dev }"

test:
	.venv\Scripts\python.exe -m pytest -q

stop:
	docker compose down
