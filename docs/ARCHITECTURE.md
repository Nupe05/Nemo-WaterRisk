# Architecture

## Data flow

```
                 ┌──────────────────────────────────────────────┐
                 │                Orchestrator                   │
                 │   build_pipeline()      distribution_sweep()  │
                 └───────┬───────────────────────────┬──────────┘
                         │                            │
        ┌────────────────▼───────────┐        ┌───────▼────────────┐
        │  DataPipelineAgent          │        │ DistributionAgent  │
        │  USGS / NOAA / EPA → PostGIS│        │ runs APPROVED only │
        └────────────────┬───────────┘        └───────▲────────────┘
                         │                            │
        ┌────────────────▼───────────┐                │
        │  ScoringAgent               │        ┌───────┴────────────┐
        │  RawDataRecord → Score      │        │   Approval queue    │
        │  emits RiskChange (Δ ≥ thr) │        │  (ApprovalItem)     │
        └────────────────┬───────────┘        │  human decides in   │
                         │                     │  Django admin       │
     ┌───────────────────┼─────────────┐      └───────▲────────────┘
     │                   │             │              │
┌────▼─────┐     ┌───────▼──────┐  ┌───▼──────────┐   │ queue_for_approval()
│ReportAgent│    │ ContentAgent │  │ VisualAgent  │───┘
│ PDF + gate│    │ 3 platforms  │  │ Matplotlib   │
└──────────┘     └──────────────┘  └──────────────┘
```

## The approval gate (the one invariant)

`ApprovalItem` is the single choke point. Agents call
`BaseAgent.queue_for_approval(action_type=…, payload=…)`, which validates the
action type against `ApprovalItem.ActionType` and writes a `PENDING` row. The
`action_runner`:

- refuses to execute anything whose state is not `APPROVED`
  (`execute_item` raises `ActionError` otherwise), and
- re-validates file paths against `NEMO_WORKSPACE_ROOT` at execution time.

There is exactly **one** action vocabulary shared by proposer and runner, so an
agent can never propose something the runner will silently mishandle, and the
runner can never run something an agent didn't route through approval.

## Why ORM instead of a JSON state store

The previous system did read-modify-write on a JSON file per task; with two
concurrent workers that loses updates. Here all state is in PostgreSQL and
mutations use normal Django transactions and `update_fields`, so concurrent
orchestrator/Celery workers are safe.

## Scoring model

`scoring/model.py` is deliberately LLM-free and deterministic — it's the
credibility core. A weighted blend of streamflow deficit (0.45), precipitation
deficit (0.30), and withdrawal pressure (0.25), each normalized to 0–1, scaled
to 0–100. Baselines are placeholders; replace with per-watershed historical
percentiles once you have history. The LLM is used only for *narrative prose*
in reports and for drafting marketing content — never for the numbers.

## Secrets

- LLM key: `ANTHROPIC_API_KEY` (env only).
- Mailbox OAuth tokens: Fernet-encrypted via `core.crypto` before hitting the
  DB; key from `NEMO_TOKEN_KEY`.
- `.env`, `workspace/`, and `*.pdf` outputs are gitignored.

## Extending

- **New external action**: add a value to `ApprovalItem.ActionType`, a handler
  in `action_runner._HANDLERS`, and an agent that proposes it. Nothing else.
- **New data source**: add a module under `integrations/`, returning the
  normalized `{metric, value, unit, observed_at, raw}` shape, and call it from
  `DataPipelineAgent`.
- **Real posting**: replace the `_run_post_*` stubs with tweepy /
  google-api-python-client / Instagram Graph calls, reading credentials from env.
```
