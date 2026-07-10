# Demo narration script

Written for a confident, direct, "here's what this actually does" tone —
like walking a client through a real product, not reciting a feature list.
Roughly 90 seconds if read at a natural pace. Pair with the recorded GIF
(`~/Downloads/hvac-analyzer-demo.gif`) or your own screen recording
following the same path: Dashboard → Ingest → Bills → Zone Reports →
Anomalies → Settings.

---

**[Dashboard — 30D view]**

"This is the HVAC Efficiency Analyzer. It answers one question I couldn't
get a straight answer to anywhere else: which of my two AC units is actually
costing more to run, and why.

Every number here is real — this is a live household, not a demo dataset.
Real utility usage, split across units by their real runtime share, plotted
against real hourly weather. Twenty-three anomalies flagged this month, nine
of them critical — that's not noise, that's the system telling me something
is actually wrong."

**[Ingest]**

"Everything comes in here. Green Button interval exports from the utility,
bill PDFs, and monthly thermostat runtime reports — all parsed automatically.
No vendor-specific template, no manual data entry. I drop in whatever PDF
the utility or thermostat vendor sends me, and Claude extracts the
structured data — rate schedule, tier breakdown, past-due balances, per-zone
runtime hours."

**[Bills]**

"This is the real rate history it derived — down to the exact tier
breakdown per billing period — automatically reconciled against the actual
usage data. If a bill has a late fee or a past-due carryover, it's flagged
separately so it never gets miscounted as electricity cost."

**[Zone Reports]**

"Since I don't have live thermostat API access yet — that's a real,
disclosed limitation, not something hidden — this is the workaround: real
monthly runtime reports from the thermostat vendor, grouped by month so it's
actually readable, not a wall of disconnected rows."

**[Anomalies]**

"And this is where it gets interesting. Every one of these is cross-
referenced against real weather for that exact day — energy usage that's
disproportionate to how hot or cold it actually was, efficiency trending the
wrong direction, heating that ran on a day it had no business running. Every
timestamp respects the property's real local timezone — that sounds like a
small detail, but getting it wrong is exactly the kind of bug that makes you
distrust every other number in the app."

**[Settings]**

"And the whole thing is honest about what it knows versus what it's
inferring — timezone auto-detected from the property's real coordinates, no
manual entry, and every data point in the app is tagged by how much to trust
it: measured, estimated, or placeholder. Nothing pretends to be more certain
than it is."

---

## Notes for whoever records this

- The property name/address/ZIP are already either generic or blank in this
  recording — don't add real identifying details when you record your own
  pass.
- Feel free to cut/reorder scenes to match your own pacing; the six-page
  path above is the minimum that shows the actual differentiator (real
  cross-source data fusion), not just a pretty dashboard.
