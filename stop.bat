@echo off
REM Stop docker services and kill local dev servers (Windows)
@echo Stopping docker containers...
docker compose down

REM Kill common dev servers (vite, flask) if running
for /f "tokens=2" %%p in ('netstat -aon ^| findstr ":5173"') do (taskkill /PID %%p /F) >nul 2>&1
for /f "tokens=2" %%p in ('netstat -aon ^| findstr ":5000"') do (taskkill /PID %%p /F) >nul 2>&1
@echo Done.
