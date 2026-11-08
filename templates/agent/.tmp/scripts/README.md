# `.tmp/scripts/` — shared execution utilities

Python modules used by **two or more** skills. Tracked in git (the rest of `.tmp/`
is scratch). `agents.py` puts this folder on `PYTHONPATH` for hosted runs; a skill
script run by hand adds it itself:

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[4] / ".tmp" / "scripts"))
from run_store import new_run, save_step, finish_run
```

| Module | Purpose |
|---|---|
| `run_store.py` | One folder per run under `outputs/`: inputs, step files, status; search past runs |

## Promotion path (DOE)

```
one-off script in .tmp/            used once
      │  needed by a second run or skill
      ▼
.tmp/scripts/<module>.py           shared, tested, domain-agnostic
      │  grows into a multi-step domain workflow
      ▼
.github/skills/<name>/             SKILL.md + scripts/ + tests/
```

Code used by one skill stays in that skill's `scripts/`. Every module here has a
test (in the skill that depends on it, or `tests/`), because two skills break when
it does.
