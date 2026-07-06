# Data-Center Siting Index ("where to build")

The water index answers *"how risky is the site I picked?"* This module answers
the more valuable, upstream question: *"where should I build?"* It ranks the
major U.S. data-center markets on the three factors that actually decide a
build, then sells the county-level detail — the same free-teaser / paid-report
model as the water product.

## The score

Each candidate **county** gets three 0–100 favorability legs (higher = better),
blended into a composite suitability score and a letter grade
(Prime / Strong / Viable / Marginal / Challenged):

| Leg | Weight | Source | Why it matters |
|-----|--------|--------|----------------|
| **Power** | 40% | ISO/RTO interconnection-queue backlog & time-to-energize (LBNL "Queued Up", ISO reports, EIA) | The #1 binding constraint today — a 4–7 yr queue kills projects. |
| **Water** | 35% | USGS water/streamflow context + U.S. Drought Monitor climatology | Our differentiator; the emerging #2 constraint (AZ, UT, NV, GA). |
| **Hazard** | 25% | FEMA National Risk Index (county) | Drives insurance cost and cooling load (heat). |

Counties roll up to **metro markets** (population of candidate counties per
market), and markets are ranked nationally. Direction is the opposite of the
water-*risk* score on purpose: here **higher = better site**, so the two are
never confused.

Weights are configurable without a code change:

```bash
heroku config:set NEMO_SITING_WEIGHTS="power:0.45,water:0.35,hazard:0.20" -a water-risk
```

## Data honesty (v1)

Power, water-headroom, and hazard values are **curated, sourced snapshots** of
slow-moving structural factors (interconnection regime, basin yield, seismic
exposure) — the same pattern as the census population table. They're grounded
in the public sources above and documented inline in
`integrations/grid.py`, `integrations/hazard.py`, and
`integrations/siting_locations.py`. Reports state plainly that scores are
*relative rankings for shortlisting*, to be confirmed with site-specific
utility and water-rights diligence.

### Live data & provenance (data hardening)

Each leg records its data source in `SitingScore.detail`, and the scored value
reflects live conditions where a live signal genuinely improves the answer:

- **Water — live.** The structural basin baseline is discounted by the county's
  *current* U.S. Drought Monitor DSCI (fetched live, tokenless), removing up to
  `NEMO_WATER_DROUGHT_PENALTY` of headroom at maximum drought. Falls back to the
  structural baseline if the feed is unavailable. Provenance:
  `"structural + USDM drought (live)"` or `"structural"`.
- **Hazard — structural, by design.** We fetch FEMA's National Risk Index rating
  live and show it as authoritative *context* (the `FEMA NRI` column), but we do
  **not** drive the hazard leg from the NRI composite. That composite is weighted
  by expected annual loss and scales with population/property value, so large
  metros (Cook, Santa Clara, Maricopa) pin near 100 "Very High" on exposure
  alone — the wrong signal for siting a single asset. The hazard leg stays our
  physical-hazard model (which hazards actually threaten a facility).
- **Power — sourced snapshot.** Interconnection queues have no live API; the leg
  is a periodically-refreshed snapshot of the authoritative annual dataset
  (LBNL "Queued Up" + ISO reports), labelled as such.

Toggle all live fetches with `NEMO_SITING_LIVE` (default on; set `0` for
offline/testing). Attribution: this product uses FEMA's National Risk Index but
is not endorsed by FEMA.

## Run it

```bash
python manage.py score_siting          # scores every candidate county, prints the national top 10
```

Wire it to Heroku Scheduler (weekly is plenty — these factors move slowly):

```bash
heroku addons:open scheduler -a water-risk   # add: python manage.py score_siting
```

## The pages

- **`/siting/`** — free public teaser: markets ranked best-first, each with its
  composite grade and the three headline legs. Lead magnet.
- **`/siting/<market>/`** — public market page: market score + legs + best
  submarket, with a signup to unlock the county detail.
- **`/siting/report/<market>/`** — the paid deliverable (staff-gated): full
  county-by-county breakdown, key hazards, established-vs-emerging submarkets.
  `?pdf=1` renders a PDF when WeasyPrint's libs are present, else printable HTML.

## The revenue loop (same as water)

A signup on a market drops an **approval-gated** `SEND_SITING_REPORT` item into
the queue (admin → Approval items). Nothing emails automatically — you approve
it, and the next distribution sweep renders the email-safe report and sends it
from `DEFAULT_FROM_EMAIL`. Leads land under admin → Leads with
`source = siting_index`.

## What's isolated

This brick is additive. It doesn't touch the water pipeline, scoring, inbound
email, or social posting. New surface only: two models (`SitingLocation`,
`SitingScore`), migration `0004_siting`, `agents/siting_agent.py`,
`scoring/siting.py`, `integrations/{grid,hazard,siting_locations}.py`,
`core/siting_views.py`, four templates, and one new approval action
(`SEND_SITING_REPORT`).
