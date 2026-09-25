# FP Feedback & Whitelist

`scripts/fp_feedback.py` turns rejected bugs into reusable suppressions so the same false positive does not become a new finding every round.

## Pattern file

`.bug-hunter/fp_patterns.json`

```json
{
  "version": 1,
  "patterns": [
    {
      "id": "fp-0001",
      "match": "selector+rule+route",
      "modality": "web-visual",
      "category": "ui-layout",
      "rule_id": "touch-target",
      "route": "/",
      "selector_pattern": "[data-testid=btn-tiny]",
      "reason": "decorative chip",
      "source_bug_id": "bug-0007"
    }
  ]
}
```

## Match modes

| Mode | Hits when |
|------|-----------|
| `exact` | modality+category+rule+route+viewport+selector |
| `selector+rule+route` | rule + selector + route |
| `rule+route` | rule + route |
| `digest` | `core_assertion_digest` equal |

## Semantics

- Matching findings are marked `status: suppressed` with `suppressed_by`.
- Suppressed findings are still fingerprint-registered (anti-rescan noise).
- `hunt_round` summary counts them in `suppressed_count`, **not** `new_count`.

## CLI

```bash
python scripts/fp_feedback.py absorb --root . --bug .bug-hunter/bugs/rejected/bug-0007.json
python scripts/fp_feedback.py add --root . --rule-id touch-target --route / --selector "[data-testid=x]" --reason "chip"
python scripts/fp_feedback.py list --root .
python scripts/fp_feedback.py check --root . --finding path/to/finding.json
python scripts/fp_feedback.py remove --root . --id fp-0001
python scripts/fp_feedback.py agents-snippet --root . --out AGENTS.bug-hunter.snippet.md
python scripts/fp_feedback.py apply --root . --findings findings.json --out marked.json
```

`agents-snippet` writes a **suggested** markdown file only. It never edits the project `AGENTS.md`.
