Quick guide — run Postgres locally with Docker

1) Start Postgres + Adminer:

   docker compose up -d

2) Connection details (defaults in docker-compose.yml):

   - Host: localhost
   - Port: 5432
   - User: postgres
   - Password: postgres
   - Database: ecommerce

   Adminer UI: http://localhost:8080 (select PostgreSQL, fill credentials above)

3) Point your Flask app to the DB by setting the environment variable `DATABASE_URL`:

   Example (PowerShell):
     $env:DATABASE_URL = 'postgresql://postgres:postgres@localhost:5432/ecommerce'
     C:/Users/Samuel/Desktop/eCommerce/.venv/Scripts/python.exe app.py

4) Notes / pitfalls:
   - Data persists in a Docker volume `pgdata` (survives restarts).
   - Do NOT expose Postgres to the public internet without hardening and firewall rules.
   - If you use Windows WSL2/docker Desktop, `localhost:5432` should work; otherwise use the Docker host IP.
