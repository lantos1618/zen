# Jev test review

A good test checks a specific, meaningful contract with an observable result that a plausible bug would change. It should be reproducible, have justified expectations, and exercise the relevant boundary without merely duplicating implementation logic. Compilation success can itself be the oracle for a compiler regression. Actual broken-implementation controls provide stronger evidence than static scores.

Run from the repository root:

```sh
python3 tests/quality/jev_test_review.py
python3 tests/quality/jev_test_review.py --run --jobs 6
python3 -m unittest discover -s tests/quality -p test_jev_test_review.py
```

The first command inventories the canonical `tests/run.py` cases and rebuilds reports offline. The second sends source, expected outputs/diagnostics, fixtures, and harness metadata to TypeSafe at `https://api.typesafe.ai/v1/systemone`, using pinned model `jev-1.13.0`. Use it only for an authorized corpus. The key is prompted without echo, or read from `TYPESAFE_API_KEY`; it is not saved. Requests do not follow redirects. Completed results are reused only when the complete request hash matches; changed inputs or questions require a fresh assessment.

Outputs under ignored `build/source_health/jev-test-review/`:

- `review.html`: standalone searchable review browser, including source and expectations.
- `reviews.json`: one ranked record per test, all questions, raw answers, probabilities, confidence and usage.
- `files.json`: each source/fixture/expectation file mapped to its test assessments.
- `inventory.json`: local source inventory and harness metadata.
- `responses/`: resumable request-hash cache.

Quality weights are clarity 15%, oracle strength 35%, likely bug sensitivity 30%, boundary coverage 10%, determinism 10%. Scores are scaled from 0–4 to 0–100. Review priority is 100 minus quality, plus 20 for incomplete context and 10 for recommendation confidence below 60%. Highest priority receives rank 1. Confidence is the model recommendation confidence, not an empirically calibrated correctness probability.

These are static suggestions. Jev does not execute tests, mutations, sanitizers or the compiler. Do not delete tests on score alone. Inspect source and the relevant compiler/library contract; demonstrate a plausible failing control when strengthening a test. Exact-content duplicate candidates do not establish semantic redundancy. This inventory covers the canonical corpus, not every separate quality or sanitizer script. Files and reports contain repository source and should be treated accordingly.

## Comparing a strengthening pass

Save `reviews.json` and `inventory.json` before editing the corpus. Use
`--compare PATH/TO/reviews.json --filter EXACT_TEST_ID --run --force` to obtain
a fresh assessment with the same model and questions. Repeat `--filter` for
multiple cases. The reports show prior score, delta and whether source/oracle
content changed. `comparison.json` includes the originally flagged cases.
Reassessing unchanged cases provides an indication of review variability; an
improved score alone is not evidence of better fault detection.

`python3 tests/quality/strengthened_oracles.py` compiles five clean fixtures and
five deliberately faulty generated-C variants. Every variant must compile;
clean results must match and faulty results must differ. Optional
`--baseline-tests PATH` repeats those controls against a saved original corpus.
Reports stay under `build/source_health/jev-test-review/oracle-controls`.
These are explicit simulations of bad lowering, not comprehensive mutation
coverage of the compiler source. They cover discarded nested-field returns,
zeroed generic returns, omitted actor handlers, omitted destruction and
insufficient allocator alignment.

## Separate code-smell classification

`python3 tests/quality/jev_code_smells.py` inventories maintained code offline.
`--run` sends the numbered source windows to the same official TypeSafe endpoint;
this broader source payload needs authorization separate from a test-only review.
The code-smell pass must not be represented as complete before responses exist.

The five independent questions cover actors, memory, structured text, matches,
and nesting. Each has concrete subtype choices plus `none_visible`,
`intentional`, and `context_needed`. A sixth question separates maintainability
from possible/likely correctness concerns. Confidence is model confidence only.
Jev cannot generate explanations or exact line selections here: reported line
ranges identify source windows, not proven offending lines. All source in each
eligible file is covered by bounded windows; long stress lines are split and
retain their original line number. Cross-window/cross-file reasoning remains a
limitation. No filename/depth heuristic alone declares a bug.

Generated/vendor paths, symlinks, missing files and non-code files are explicitly
listed as not reviewed. Git-ignored build output and private environment files
are outside the code inventory. Reports are separate from test-quality scores
under `build/source_health/jev-code-smells/`: `inventory.json`, `files.json`,
`review.html`, and request-hash response caches. Unchanged successful requests
resume without another API call; errors are retried on the next run.

Examples in the rubric include manual LSP JSON that correctly escapes values
(a maintainability candidate, not evidence of injection), the intentional
owning-storage reproducer, typed per-turn request encoding, explicit actor join
ordering, one-sided boolean matches, and necessary TLS retry-state branches.
