# Engineering memory

Use `events.jsonl` for compact, append-only records of material incidents,
non-obvious fixes, consequential decisions, accepted limitations, and failed
approaches worth avoiding. Do not record routine edits.

Each line is one JSON object. Use only fields that add value, selected from
`id`, `timestamp`, `area`, `type`, `symptom`, `evidence`, `decision`,
`rationale`, `status`, `revisit_when`, and `related`.

Records are historical evidence rather than permanent instructions. Reassess
them against current requirements and repository evidence. Never store secrets,
personal data, or bulky raw logs here.
