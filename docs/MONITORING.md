# Monitoring & Alerts (recurring revenue)

One-off reports are a sale; monitoring is a **subscription**. This module lets a
customer subscribe to a water-risk site *or* a siting metro and get an
approval-gated email whenever that target's risk moves against them — turning
the `RiskChange` / `SitingChange` signals the platform already produces into
recurring MRR.

Billing is a separate, later brick: `tier` (Basic / Pro) is already modeled so
the alert logic honors it, but signup is free for now. Stripe checkout + paid
gating come next.

## How it works

1. **Signup** — a "Monitor this site/market" form on each detail page creates a
   `MonitorSubscription` (email, target, tier). Idempotent per target.
2. **Sweep** — `run_alerts` runs the `MonitorAgent`: for every active
   subscription it compares the target's current score to the state we last
   alerted on. Direction is handled per product so *worse always means worse*:
   - **water site** — score is 0-100 where **higher = worse**
   - **siting metro** — score is 0-100 where **higher = better**, so a **drop** is worse
3. **Alert** — if the risk crossed into a worse band, or moved adversely past
   the subscriber's tier threshold, the agent drafts a `SEND_ALERT` email into
   the **approval queue**. Nothing sends until you approve — same gate as
   everything else. On approval, the distribution sweep emails the alert.
4. **Dedupe** — each subscription stores `last_alerted_score/band`; we only
   alert when the current adverse state differs from what we already sent, and
   silently rebaseline on material improvement (no "good news" spam).

## Tiers

| Tier | Alerts when… |
|------|--------------|
| Basic | risk crosses into a worse band, or moves adversely ≥ 7 points |
| Pro | risk crosses into a worse band, or moves adversely ≥ 3 points |

A band/grade crossing always alerts regardless of tier. Override the point
thresholds with `NEMO_ALERT_DELTA_BASIC` / `NEMO_ALERT_DELTA_PRO`.

## Run it

```bash
python manage.py run_alerts            # sweeps subscriptions, queues approval-gated alerts
```

Wire to Heroku Scheduler **after** `daily_refresh` and `score_siting` so alerts
reflect the freshest scores. Suggested: daily, a few minutes past those jobs.

The `SitingChange` emitter is built into `score_siting`: when a metro's
rolled-up suitability moves ≥ `NEMO_SITING_CHANGE_THRESHOLD` (default 3.0)
between runs, it records a `SitingChange` (parity with the water `RiskChange`).

## The revenue loop

Signup → `MonitorSubscription` (+ a `Lead` with `source=monitor_signup`).
Adverse move → approval-gated `SEND_ALERT`. You approve → the existing
distribution sweep sends it. Every alert is recorded as an `AlertEvent` (admin →
Alert events) with the exact transition and the linked approval, so you have a
full audit trail.

## What's isolated

Additive only. New: `MonitorSubscription`, `AlertEvent`, `SitingChange` models,
migration `0005`, `agents/monitor_agent.py`, `run_alerts` command, a
`SEND_ALERT` action + `alert_email.html`, a `monitor_subscribe` view, and signup
forms on the two detail pages. The water pipeline, siting scoring, inbound
email, and social posting are untouched (the siting agent only gains change
emission).
