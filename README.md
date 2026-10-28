# Daily Dispatch

A Django news application. Journalists (independent or at a publisher)
write articles, editors approve them, and readers subscribe to
publishers and journalists. Includes a token-authenticated REST API.

## Contents
- [Run with venv](#run-with-venv)
- [Run with Docker](#run-with-docker)
- [Secrets](#secrets)
- [Documentation](#documentation)

## Run with venv
```bash
git clone https://github.com/juvi-gis/daily-dispatch.git
cd daily-dispatch
python -m venv venv
venv\Scripts\activate          # macOS/Linux: source venv/bin/activate
pip install -r requirements.txt
copy .env.example .env         # macOS/Linux: cp .env.example .env
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```
Leave `DB_HOST` empty in `.env` to use SQLite, or fill in the
`DB_*` values to use your own MariaDB/MySQL server.

## Run with Docker
Fill in `.env` first (see Secrets), then start the app and a MariaDB
container together:
```bash
docker compose up --build
```
Open http://localhost:8000. To run only the web image against your
own database:
```bash
docker build -t daily-dispatch .
docker run --env-file .env -p 8000:8000 daily-dispatch
```

## Secrets
`.env` is ignored by Git and must never be committed. Copy
`.env.example` to `.env` and set:

| Category | Variables | Description |
| --- | --- | --- |
| Django | `SECRET_KEY` | Django secret key |
| Database | `DB_NAME`, `DB_USER`, `DB_PASSWORD` | Database credentials |
| Database | `DB_HOST`, `DB_PORT` | Database host and port (empty host = SQLite) |
| Email (SMTP) | `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_USE_TLS` | SMTP server settings (defaults suit Gmail) |
| Email (SMTP) | `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD` | SMTP login. Leave both empty and approval emails print to the console instead of being sent. |

Generate a secret key:
```bash
python -c "from django.core.management.utils import get_random_secret_key as k; print(k())"
```

## Documentation
Built Sphinx HTML lives in `docs/`. Open `docs/index.html`. To rebuild:
```bash
pip install sphinx
sphinx-build -b html docs_src docs
```
