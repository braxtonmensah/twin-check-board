# Preregistration: twin-check board, first run

Written and pushed on 2026-10-27 (US Eastern) before any workflow run of this repository produced a number.
The git history shows this file landing before the first `board` run. Nothing below is edited after results;
later changes go in a dated addendum at the end.

## What is measured
For each split in `splits.json`: the percent of test rows whose closest training row has a Levenshtein ratio
of 0.80 or above (twin rate), and the percent with a verbatim training match (exact rate), as reported by
`braxtonmensah/twin-check@v1` called as a remote action. Inputs are fetched from each benchmark's own URL and
must match a pinned sha256. These are overlap rates. They are not score inflation and nothing is retrained.

## Cross-check rule (fixed now)
A row with a `record_id` passes only if the action's two-decimal twin and exact strings, and n_train and
n_test where the record lists them, are equal as strings to https://silicyte.com/data/leakage-measurements.json
at run time. The corrected LRGB split passes only at twin 0.00 and exact 0.00. Any FAIL blocks publication;
the board is not edited by hand to make a row pass.

Rows expected to PASS: record ids 1 (LRGB Peptides-func 65.29 / 7.72), 2 (AMPlify positives 63.47 / 0.00),
12 (AMPlify negatives balanced 30.18 / 0.00), 6 (FLIP meltome mixed 0.29 / 0.00), 7 (meltome human 0.05),
8 (meltome human_cell 0.00), 9 (FLIP scl mixed_hard 0.00), and the corrected LRGB split (0.00 / 0.00).

## The two FLIP FASTA rows (ids 10 and 11)
While building this board, the record's script (`thirdparty/verify_sweep.py`, function `flip_fasta`, in
braxtonmensah/silicyte-design-loops) was read: it measures the strings in `splits/sampled.fasta`. FLIP's own
secondary_structure README (commit 62cace8) says `sampled.fasta` is the labels file ("H for helix, E for sheet,
C for coil") and that sequences are in `splits/sequences.fasta`. That is not yet checked on the bytes here. The board therefore runs both:
- method-check rows reproduce the record's computation on `sampled.fasta`. Registered expectation: they
  reproduce 0.00 (conservation) and 65.38 (secondary_structure, n_train 10792, n_test 364) exactly.
- sequence rows join the split ids to `sequences.fasta` and measure amino-acid sequences.
The prepare log prints the alphabet of each file, so whether `sampled.fasta` holds labels is checkable.

Decision rule, fixed now: if the method checks reproduce the record AND the `sampled.fasta` alphabet is a
label alphabet (for example C, E, H) rather than amino acids, then record ids 10 and 11 were computed on labels,
and the sequence rows are the correct measurement. That is reported to Silicyte for a public correction of the
record and of its headline claim, whatever the sequence rows read. This board does not edit the record.
No prediction is registered for the sequence rows' values.

## New rows (not in the record)
AMPlify negatives imbalanced; FLIP scl mixed_soft, human_hard, human_soft, balanced, mixed_vs_human_2.
No value predictions. They are reported as measured, labelled `new`.

## Excluded, and why
PepBenchmark (record id 3) and AMP Scanner v2 (ids 4 and 5) are on the record but not on this board: no license
stating that download and processing is allowed was found for their data files (the PepBenchData dataset card
on Hugging Face declares no license; the AMP Scanner v2 download page states none). They can be added by PR if
a license is identified.
