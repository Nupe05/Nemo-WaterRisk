# Install & run

## 1. System prerequisites

PostGIS needs GDAL/GEOS/PROJ, and WeasyPrint needs Pango/Cairo.

**macOS (Homebrew):**
```bash
brew install postgresql postgis gdal geos proj pango cairo redis
brew services start postgresql
brew services start redis
```

## 2. Database

```bash
createdb nemo_waterrisk
psql nemo_waterrisk -c "CREATE EXTENSION postgis;"
# optional dedicated role:
psql nemo_waterrisk -c "CREATE ROLE nemo LOGIN PASSWORD 'nemo'; GRANT ALL ON DATABASE nemo_waterrisk TO nemo;"
```

## 3. Python environment

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

## 4. Configure

```bash
cp .env.example .env
```

Fill in at minimum:
- `DATABASE_URL` — e.g. `postgis://nemo:nemo@localhost:5432/nemo_waterrisk`
- `ANTHROPIC_API_KEY` and `NEMO_LLM_MODEL` (e.g. `claude-sonnet-5`)
- `NEMO_TOKEN_KEY` — generate with:
  `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`

## 5. Migrate & seed

```bash
python manage.py migrate
python manage.py seed_demo          # demo watershed + site + sample data
python manage.py createsuperuser
```

## 6. Run the pipeline

```bash
# draft everything (ingest -> score -> content) — no external actions
python manage.py run_orchestrator --stage build

# review the approval queue
python manage.py runserver          # visit http://127.0.0.1:8000/admin

# after approving items, push them
python manage.py run_orchestrator --stage distribute
```

Public Water Risk Index endpoint: `http://127.0.0.1:8000/index/`

## 7. Scheduled runs (production)

Either cron the management command, or use Celery beat (schedule already
defined in `config/celery.py`):

```bash
celery -A config worker -l info
celery -A config beat -l info
```

## 8. Tests

```bash
pytest                      # full suite (needs the test DB)
pytest tests/test_scoring.py   # pure scoring tests, no DB
```

## Notes on stubs

Distribution handlers for X / YouTube / Instagram and the report emailer are
**intentional stubs** that log instead of posting until you set the matching
credentials in `.env`. This lets you run the whole loop safely end-to-end
before anything is live.
