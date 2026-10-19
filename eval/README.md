# Dr.Listner evaluation harness

This harness scores saved flags against synthetic answer keys. It uses Python's
standard library and Pydantic; it makes no model or network calls. The committed
`fake-*` runs exercise the harness and are **not detector accuracy results**.

## Run locally

From the repository root, using the existing virtual environment:

```sh
.venv/bin/python -m scripts.run_eval --run fake-dev-oracle --split dev
.venv/bin/python -m scripts.run_eval --run fake-test-oracle --split test
.venv/bin/python -m scripts.run_eval --run fake-dev-drop2 --split dev
.venv/bin/python -m scripts.make_results_table --run fake-dev-drop2
.venv/bin/python -m pytest -q
```

Use `--run YOUR_ENGINE_RUN` to evaluate an engine export. Omit `--run` from
`make_results_table` to print all saved results, including clearly labeled fake
runs. Tables format saved values; they never calculate scores or intervals.

The CLI writes `eval/results/<run_id>.json`, `<run_id>.csv`, and
`<run_id>_errors.csv`. Re-evaluation replaces those files. Identical inputs produce
identical artifacts apart from the JSON timestamp and Git commit. Each file is
replaced atomically, but the three-file set is not a transactional write.

## Input contract

```text
eval/runs/<run_id>/run_meta.json
eval/runs/<run_id>/flags/<visit_id>.json
data/eval/<split>/answer_keys/<visit_id>.json
data/eval/<split>/transcripts/<visit_id>.json
data/eval/<split>/charts/<visit_id>.json
```

Metadata contains exactly `run_id`, `system` (`drlistner` or `baseline`), `mode`
(`DEMO` or `LIVE`), `model`, and `split` (`dev` or `test`). A flags file is a JSON
list of `src.schemas.Flag` objects. Every visit needs a file: write `[]` for no
flags. Missing files, unknown visits, malformed JSON, invalid flags, and metadata
mismatches cause a nonzero exit and file-specific errors before results are
written. Existing results from an earlier successful run are retained on input
failure; do not treat them as output from the failed command.

Visits are processed in filename order; flags and planted gaps retain file order.
Duplicate flag IDs do not collapse occurrences. Cross-visit flags are rejected.
The scorer validates flag shape but does not repeat the engine's semantic or
quote verification. Emitted quotes can contain the engine's de-identification
markers, whereas FN quotes come from the synthetic dataset.

`--data-root`, `--runs-root`, and `--results-root` support isolated fixture runs.
The Markdown command accepts only `--results-root` and optional `--run`; it reads
only immediate `*.json` result files. Missing counts or confidence intervals are
reported rather than fabricated.

## Matching and metrics

- Only `verified=True` flags are scored, following SPEC section 10. All other
  flags appear as `EXCLUDED` in the JSON audit. Dismissed flags remain scored.
- Each verified flag matches the first available same-type gap in key order.
  Missed questions match checklist IDs; concerns and comprehension gaps match
  transcript indices; contradictions match a chart ID **or** a transcript index.
  Both comprehension edit operations follow the transcript-pointer rule.
- TP is a matched flag; FP is an unmatched flag, including duplicates and flags
  on clean visits; FN is an unmatched planted gap. Counts are micro-aggregated
  per type and overall. The scorer does not seek a maximum matching.
- Precision is `TP/(TP+FP)` and recall is `TP/(TP+FN)`. F1 is
  `2*TP/(2*TP+FP+FN)`. A zero denominator yields JSON `null`, an empty CSV cell,
  or an em dash in Markdown. In particular, F1 is zero when gaps or predictions
  exist but none match, and null when neither exists.
- False flags per visit is total FP divided by visits. Clean-visit FP and the
  number of clean visits are also saved. Wilson 95% intervals use scored
  predictions for precision and planted gaps for recall, with null bounds for
  an empty denominator. Counts accompany all reported rates.
- Too-early flags are scored missed questions or concerns emitted before the
  key's `wrap_up_turn`, including FPs. Null emission times mean end-of-visit.
  Explicit times with missing wrap-up are counted as unassessable, not as zero
  delay or proven on-time behavior.
- Turns-to-detection covers matched contradictions and comprehension gaps only:
  emission turn minus the gap's first recorded turn. The JSON saves raw delays,
  mean, median, missing-time count, and negative-delay count. Missing times are
  excluded from averages; negative delays remain visible as anomalies.

The JSON top level validates as `EvalResult` after removing `extras`. Extras hold
count denominators, intervals, timing, exclusions, fake-run status, verification
policy, and per-visit assignments. Reading grade and plan coverage remain null.
The recorded `git_commit` is the checkout HEAD when the evaluator runs; it does
not attest that the worktree or exported engine inputs were unchanged.

The errors CSV has one row per FP/FN, with visit/type, original flag/gap indices,
IDs, reason, evidence JSON, and rationale or edit description. For missed-question
FNs, evidence is a checklist ID and deletion indices refer to the **base** visit;
no nonexistent quote is invented. Other FN evidence references the final visit
and chart. Runs without errors produce a header-only errors CSV. Exclusions are
audited in JSON and do not appear as FP rows.

## Generate fake runs

```sh
.venv/bin/python -m eval.fake_runs --run my-fake-dev --split dev --scenario oracle
.venv/bin/python -m eval.fake_runs --run my-drop-dev --split dev --scenario drop --count 2 --type missed_question
.venv/bin/python -m scripts.run_eval --run my-drop-dev --split dev
```

Scenarios: `oracle`, `drop`, `extra`, `wrong-type`, `clean`, `early`, `duplicates`.
Mutation counts apply across the split in file order. `--type` restricts `drop`,
`wrong-type`, `early`, and `duplicates`; `extra` and `clean` add false concerns to
a gapped or clean visit respectively. Impossible mutations fail explicitly.
The generator refuses to overwrite an existing run directory. Its `FAKE/` model
prefix, saved recipe, and result marker distinguish constructed flags from
detector output. Fake flags are schema-valid and source their quotes from the
dataset; their verification bit is a test fixture, not an LLM decision.

## Limitations and contract questions for review

The data is synthetic, the FHIR-lite charts are hand-authored, and the phrase
pools have limited variety. There is no clinician validation. Gap-4 cues are our
own draft; finding these cues does not establish real-world comprehension-gap
detection. Small counts produce wide intervals. Wilson intervals treat trials as
independent and do not account for correlations within visits or phrase families.
Unplanted genuine gaps count as FPs under the answer-key contract. No thresholds
are tuned to the test split; fake test runs validate scoring only.

No shared schema or SPEC files were edited. These decisions need to be made
explicit in the shared contract:

- SPEC section 4 describes a baseline without a verifier, while section 10
  requires verified flags. This harness applies section 10 to **both** systems
  and reports exclusions; it never promotes baseline flags to verified. Before
  a real baseline comparison, clarify which component sets that bit.
- Record the F1 zero-denominator convention and the missing/negative timing
  behavior described above.
- Reconcile SPEC section 10's summary-coverage wording with the Phase 4 request
  to leave reading-grade and plan-coverage fields null for Phase 5.
- `EvalResult` lacks typed fields for timing, intervals, and exclusions; the
  harness keeps them in `extras` without requiring a schema change. SPEC's older
  section 2 still lists only the original gap types; matching follows section 8.
