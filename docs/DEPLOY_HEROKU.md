# Deploy to Heroku

This deploys the web app (public Water Risk Index + admin). Background agents
(Celery worker/beat) are optional and covered at the end.

Prerequisites: the Heroku CLI, logged in (`heroku login`), and this repo pushed
to GitHub (or just a local git repo).

---

## 1. (Recommended) Commit model migrations once, locally

The release step will generate them automatically if you skip this, but
committing them is cleaner and deterministic:

```bash
python manage.py makemigrations core
git add core/migrations && git commit -m "Add model migrations"
```

## 2. Create the app with the right buildpacks

GDAL/GEOS/PROJ (needed by PostGIS) are installed via the apt buildpack, which
must run **before** the Python buildpack:

```bash
heroku create nemo-water-risk           # pick your own name
heroku buildpacks:clear
heroku buildpacks:add heroku-community/apt
heroku buildpacks:add heroku/python
```

The `Aptfile` in the repo lists the system libraries to install.

## 3. Add Postgres (with PostGIS)

```bash
heroku addons:create heroku-postgresql:essential-0
```

PostGIS is enabled automatically by migration `0001_enable_postgis`. If your
plan blocks `CREATE EXTENSION`, enable it once by hand:

```bash
heroku pg:psql -c "CREATE EXTENSION IF NOT EXISTS postgis;"
```

## 4. Set config vars

```bash
heroku config:set DJANGO_DEBUG=false
heroku config:set DJANGO_SECRET_KEY="$(python -c 'import secrets;print(secrets.token_urlsafe(50))')"
heroku config:set NEMO_TOKEN_KEY="$(python -c 'from cryptography.fernet import Fernet;print(Fernet.generate_key().decode())')"
heroku config:set ANTHROPIC_API_KEY="sk-ant-..."
heroku config:set NEMO_LLM_MODEL="claude-sonnet-5"
heroku config:set DJANGO_CSRF_TRUSTED_ORIGINS="https://nemo-water-risk.herokuapp.com"
```

(Use your actual app URL in the last line.)

## 5. Deploy

```bash
git push heroku main
```

The `release` process runs migrations (creating the PostGIS extension and all
tables). Static files are collected automatically by the Python buildpack and
served by WhiteNoise.

## 6. Seed and create an admin user

```bash
heroku run python manage.py seed_demo
heroku run python manage.py createsuperuser
heroku open
```

Your public index is at `/`, the admin (and Leads inbox) at `/admin/`.

---

## Troubleshooting

**"Could not find the GDAL library" (or GEOS):** point Django at the .so files
installed by the apt buildpack:

```bash
heroku config:set GDAL_LIBRARY_PATH=/app/.apt/usr/lib/x86_64-linux-gnu/libgdal.so
heroku config:set GEOS_LIBRARY_PATH=/app/.apt/usr/lib/x86_64-linux-gnu/libgeos_c.so
```

(`settings.py` reads these env vars.) Confirm the exact path with
`heroku run "ls /app/.apt/usr/lib/x86_64-linux-gnu/ | grep -E 'gdal|geos'"`.

**collectstatic fails during build:** set `heroku config:set DISABLE_COLLECTSTATIC=1`,
deploy, then run `heroku run python manage.py collectstatic --noinput`.

---

## Optional: background agents (nightly pipeline + posting)

These need Redis and run as separate dynos:

```bash
heroku addons:create heroku-redis:mini
heroku ps:scale worker=1 beat=1
```

`REDIS_URL` is picked up automatically (settings handle Heroku's TLS `rediss://`).
Keep `worker`/`beat` at 0 (the default) until you actually want the agents running.
You can also trigger a run on demand:

```bash
heroku run python manage.py run_orchestrator --stage build
```
