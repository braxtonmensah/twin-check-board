# twin-check board

A weekly table of near-twin overlap between the train and test sets of public peptide and protein ML splits.

**Board:** https://braxtonmensah.github.io/twin-check-board/ (also [board/BOARD.md](board/BOARD.md) and
[board/board.json](board/board.json) in this repo).

## What the numbers are

- **Twin rate @0.80:** percent of test rows whose closest training row has a Levenshtein ratio of 0.80 or above.
- **Exact rate:** percent of test rows with a verbatim match in the training rows.

**These are overlap rates, not score inflation.** Nothing is retrained here, so a rate on this board does not say
how much any reported score is overstated, or that it is overstated at all. A high rate says the test set is
close to the training set at the sequence level; whether that matters depends on the task. Levenshtein ratio is a
sequence-string measure only: it says nothing about structure, function or homology found by alignment tools.

**No issue was filed on any benchmark** by this board, and none is filed automatically. It only reads files that
the benchmark authors publish.

## How it runs

`.github/workflows/board.yml` runs every Monday at 07:41 UTC and on manual dispatch:

1. `plan` reads the split ids from [`splits.json`](splits.json) and resolves the commit behind
   `braxtonmensah/twin-check@v1`.
2. `measure` (one job per split) downloads each file from the URL pinned in `splits.json`, refuses it unless its
   sha256 matches, writes train and test FASTA ([`scripts/prepare.py`](scripts/prepare.py)), and runs
   `uses: braxtonmensah/twin-check@v1` on them, the same way any outside repo would call the Action.
3. `publish` builds the table ([`scripts/build_board.py`](scripts/build_board.py)), compares rows that appear in
   Silicyte's published record (https://silicyte.com/data/leakage-measurements.json) to that record as two-decimal
   strings, and commits `board/` and `docs/` (the Pages site) only if every row passes. A failing run publishes
   nothing, so the board always shows the last run in which every row passed, with that run's id.

Every row carries its source URLs, license, n_train, n_test, both rates and the run id.

## Data and licenses

No benchmark data is stored in this repo. Each file is fetched at run time from the benchmark's own published
location, at a pinned commit where the host allows it, and checked against a sha256. Only splits whose license
allows download and processing are listed; each row links its license. LRGB is CC BY-NC 4.0: this board reads it
to compute two summary numbers and does not redistribute it.

Not listed: PepBenchmark and AMP Scanner v2, which are in Silicyte's record, because no license allowing
download and processing was found for their data files. A PR that identifies one is welcome.

## Known limits

- A split that is clean at 0.80 can still share structure or homologs below that ratio.
- The FLIP conservation and secondary_structure records in Silicyte's leakage record were computed on
  `sampled.fasta`, which FLIP documents as the per-residue label file. The board measures the amino-acid
  sequences for those two splits and shows the record's computation separately as method checks. See
  [PREREG.md](PREREG.md).
- Rates are exact for the files fetched; if a benchmark updates its files, the sha256 check fails and the row
  stops until the pin is updated by PR.

## Add a split by PR

1. Append an entry to `splits` in [`splits.json`](splits.json): `id`, `benchmark`, `split`, `kind`, `license`,
   `license_url`, `record_id: null`, `expect: null`, and `files` with each file's official `url` and `sha256`.
   Use a URL pinned to a commit or release where possible.
2. Use an existing `kind` (`fasta_pair`, `zip_csv_set`, `lrgb_pickle`, `lrgb_json_split`, `flip_fasta_join`) or
   add a small parser for a new one in `scripts/prepare.py`.
3. Open a pull request. The workflow runs on the PR, downloads your files, checks the sha256 and measures the
   split, so the result is visible in the PR's checks before anything is merged. Only data whose license allows
   download and processing can be accepted; please do not commit the data itself.

## Related

- Action: https://github.com/braxtonmensah/twin-check
- Silicyte leakage page: https://silicyte.com/benchmark-leakage

MIT licensed (code only). Built by Silicyte with AI assistance.
