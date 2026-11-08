# outputs/ — one folder per run

Written by `.tmp/scripts/run_store.py`:

```
outputs/<run-slug>/
├── run.json                 inputs, steps, status, summary — the run's record
├── step_1_<name>.json       one file per pipeline step: the contract between steps
├── step_2_<name>.json
└── <deliverables>           reports, sheets, exports the user receives
```

Nested slugs group runs by project: `outputs/<project>/<run>/`. Find past runs
with `python .tmp/scripts/run_store.py search <words>` before repeating work.
Tracked in git so the team shares results; keep large binaries out (link them).
