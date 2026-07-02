# Autonomous daily refresh

The index should update itself every day without anyone running a command.
On Heroku the simplest, cheapest way is **Heroku Scheduler** running the
`daily_refresh` management command. No Redis, no always-on worker dyno.

`daily_refresh` runs the build pipeline (ingest latest USGS/NOAA/EPA data →
rescore every watershed → draft content for any material risk change) and
prints a one-line summary. It takes **no external action** — anything it drafts
lands in the approval queue for you to review; nothing is posted automatically.

## Set it up (one time)

```bash
heroku addons:create scheduler:standard -a water-risk
heroku addons:open scheduler -a water-risk
```

In the Scheduler dashboard, **Add Job**:

- Command: `python manage.py daily_refresh`
- Frequency: **Every day at** a quiet hour (e.g. `09:00 UTC`)

That's it. Each night Heroku spins up a one-off dyno, refreshes the data, and
shuts down — a few seconds of runtime.

Dashboard-only alternative: **Resources** tab → add the **Heroku Scheduler**
add-on → **Add Job** with the same command and time.

## Verify

Run it once by hand to confirm it works end to end:

```bash
heroku run python manage.py daily_refresh -a water-risk
```

You should see a summary like:

```
daily_refresh complete: ingested=20 scored=5 changes=0 content_drafted=0
```

Then check `Scheduler → job logs` (or `heroku logs --tail`) after the first
scheduled run.

## When to graduate to Celery

Heroku Scheduler runs at most hourly and only on fixed slots. If you later need
finer scheduling, per-site alerting the moment a threshold is crossed, or
higher throughput, switch to the Celery worker/beat setup already scaffolded in
`config/celery.py` (add the `heroku-redis` add-on and scale the `worker`/`beat`
dynos). For a daily index refresh, Scheduler is the right tool.
