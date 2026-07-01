# Nemo Water Risk

An autonomous, human-in-the-loop platform that tracks **water-supply risk for
data centers** and turns that data into a revenue product (paid risk reports)
plus a content/marketing engine — all directed by one person from the Django
admin.

Built in Python (Django + PostGIS). Six agents coordinated by an orchestrator.
**Every externally-visible action is gated behind an approval queue** — the
system can draft, score, and prepare, but nothing leaves without your click.

## The agents

**Build agents (run unattended — they only touch our own database):**

- **DataPipelineAgent** — nightly ingest from USGS, NOAA, and EPA into a
  PostGIS schema. Each source is isolated so one failing API can't abort the run.
- **ScoringAgent** — recomputes a 0–100 water-risk score per watershed and
  flags any watershed that moved more than the threshold (default 5 points).
- **ReportAgent** — renders a customer PDF (WeasyPrint) from real data, then
  queues the *send* for approval.

**Marketing agents (draft only — posting is approval-gated):**

- **ContentAgent** — turns a risk change into a YouTube outline, a 7-post X
  thread, and an Instagram caption + visual brief in one LLM call.
- **VisualAgent** — renders real-data charts with Matplotlib (more credible for
  a data company than generative imagery).
- **DistributionAgent** — the only agent that touches external post APIs, and
  it executes *only* items you approved.

**Orchestrator** — `build_pipeline` (nightly draft) and `distribution_sweep`
(push approved items), runnable via Celery beat or a cron `manage.py` command.

## Your daily loop

1. Agents run overnight and fill the **Approval queue** in `/admin`.
2. You spend ~15–20 min approving / editing / rejecting.
3. The morning sweep pushes what you approved.

## What changed from the previous (Node/Discord) build

This is a fresh repo. It keeps the strong patterns and fixes the review findings:

| Prior finding | Fix here |
|---|---|
| Path validated only at draft time; runner wrote to `path\|\|target` unchecked | `action_runner` re-validates every write against a workspace jail at execution |
| Executor and runner used two different action-type lists | One shared registry: `ApprovalItem.ActionType` |
| JSON-file state store → lost updates under concurrency | ORM/PostgreSQL, transactional |
| OAuth tokens stored in plaintext | `core.crypto` Fernet-encrypts tokens at rest |
| `response.content[0].text` crashes on non-text blocks | `llm_client._extract_text` concatenates text blocks safely |
| Hardcoded invalid model string | Model is required from env (`NEMO_LLM_MODEL`) |
| No tests | Approval-gate + path-jail + scoring tests included |

## Quick start

See **INSTALL.md**. Short version:

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # fill DATABASE_URL, ANTHROPIC_API_KEY, NEMO_LLM_MODEL
python manage.py migrate
python manage.py seed_demo
python manage.py run_orchestrator --stage build
python manage.py createsuperuser && python manage.py runserver   # review /admin
```

Architecture details: **docs/ARCHITECTURE.md**.
