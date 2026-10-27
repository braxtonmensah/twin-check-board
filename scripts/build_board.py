"""Assemble the board from the per-split results of one workflow run.

usage: python -I scripts/build_board.py <artifacts-dir> <out-dir>

Reads <artifacts-dir>/<name>/result.json (written by the measure job from the twin-check step's
outputs) and meta.json (written by prepare.py), fetches the live leakage record once, and writes
<out-dir>/board.json, <out-dir>/BOARD.md, <out-dir>/index.html and <out-dir>/status.json.
Cross-check rows compare the action's two-decimal outputs to the live record as strings.
"""
import html
import json
import os
import sys
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)


def load_record(url):
    req = urllib.request.Request(url, headers={"User-Agent": "twin-check-board/1.0"})
    with urllib.request.urlopen(req, timeout=120) as r:
        rec = json.load(r)
    return {m["id"]: m for m in rec["measurements"]}


def cross_check(spec, res, record):
    """Return (status, detail, wanted)."""
    rid = spec.get("record_id")
    if spec.get("differs_from_record"):
        return "differs by design", spec["differs_from_record"], None
    if rid is None and spec.get("expect") is None:
        return "new", "not in the record", None
    if rid is None:
        want = dict(spec["expect"])
        src = "expected value stated in the split file"
    else:
        m = record.get(rid)
        if m is None:
            return "FAIL", f"record id {rid} not found in the live record", None
        want = {"twin": f"{m['twin_at_080_pct']:.2f}", "exact": f"{m['exact_overlap_pct']:.2f}"}
        if "train_rows" in m:
            want["n_train"] = m["train_rows"]
        if "test_rows" in m:
            want["n_test"] = m["test_rows"]
        src = f"live record id {rid}"
    pairs = [("twin", res["twin_rate"]), ("exact", res["exact_rate"]),
             ("n_train", res["n_train"]), ("n_test", res["n_test"])]
    bad = [f"{k} {got} != {want[k]}" for k, got in pairs if k in want and str(got) != str(want[k])]
    if bad:
        return "FAIL", f"{src}: " + "; ".join(bad), want
    return "PASS", f"{src}: " + ", ".join(f"{k} {want[k]}" for k, _ in pairs if k in want), want


def main():
    art, out = sys.argv[1], sys.argv[2]
    os.makedirs(out, exist_ok=True)
    cfg = json.load(open(os.path.join(ROOT, "splits.json"), encoding="utf-8"))
    record = load_record(cfg["record_url"])
    run_id = os.environ.get("GITHUB_RUN_ID", "local")
    run_url = (f"{os.environ.get('GITHUB_SERVER_URL', 'https://github.com')}/"
               f"{os.environ.get('GITHUB_REPOSITORY', '')}/actions/runs/{run_id}")
    tc_ref = os.environ.get("TWIN_CHECK_SHA", "")
    started = os.environ.get("RUN_STARTED", "")

    def rows_for(specs, section):
        rows = []
        for spec in specs:
            d = os.path.join(art, f"result-{spec['id']}")
            p = os.path.join(d, "result.json")
            if not os.path.exists(p):
                rows.append({"id": spec["id"], "section": section, "benchmark": spec["benchmark"],
                             "split": spec["split"], "status": "FAIL", "detail": "no result from the measure job",
                             "license": spec["license"], "license_url": spec["license_url"],
                             "source_urls": [f["url"] for f in spec["files"].values()],
                             "run_id": run_id, "run_url": run_url})
                continue
            res = json.load(open(p, encoding="utf-8"))
            meta = json.load(open(os.path.join(d, "meta.json"), encoding="utf-8"))
            status, detail, want = cross_check(spec, res, record)
            rows.append({
                "id": spec["id"], "section": section,
                "benchmark": spec["benchmark"], "split": spec["split"],
                "source_urls": [f["url"] for f in spec["files"].values()],
                "source_sha256": {k: v["sha256"] for k, v in meta["files"].items()},
                "license": spec["license"], "license_url": spec["license_url"],
                "n_train": int(res["n_train"]), "n_test": int(res["n_test"]),
                "twin_rate_080_pct": res["twin_rate"], "exact_rate_pct": res["exact_rate"],
                "record_id": spec.get("record_id"), "record_values": want,
                "status": status, "detail": detail, "note": spec.get("note", ""),
                "run_id": run_id, "run_url": run_url, "twin_check": f"braxtonmensah/twin-check@v1 ({tc_ref})",
            })
        return rows

    rows = rows_for(cfg["splits"], "split")
    checks = rows_for(cfg.get("method_checks", []), "method_check")
    board = {
        "what": "Near-twin overlap between published train and test splits: the percent of test rows whose closest training row has a Levenshtein ratio of 0.80 or above, and the percent with an exact match. These are overlap rates, not score inflation.",
        "tool": "braxtonmensah/twin-check@v1, run as a remote action",
        "twin_check_commit": tc_ref,
        "run_id": run_id, "run_url": run_url, "run_started_utc": started,
        "record_url": cfg["record_url"],
        "rows": rows, "method_checks": checks,
    }
    with open(os.path.join(out, "board.json"), "w", encoding="utf-8") as fh:
        json.dump(board, fh, indent=1)

    def md_rows(rs):
        lines = ["| split | source | license | n_train | n_test | twin @0.80 | exact | cross-check | run |",
                 "|---|---|---|---:|---:|---:|---:|---|---|"]
        for r in rs:
            src = " ".join(f"[{i + 1}]({u})" for i, u in enumerate(r["source_urls"]))
            twin = f"{r['twin_rate_080_pct']}%" if "twin_rate_080_pct" in r else "n/a"
            exact = f"{r['exact_rate_pct']}%" if "exact_rate_pct" in r else "n/a"
            num = lambda k: f"{r[k]:,}" if isinstance(r.get(k), int) else "n/a"
            lines.append(
                f"| {r['benchmark']}: {r['split']} | {src} | [{r['license']}]({r['license_url']}) | "
                f"{num('n_train')} | {num('n_test')} | {twin} | {exact} | "
                f"{r['status']} | [{r['run_id']}]({r['run_url']}) |")
        return lines

    notes = [f"- **{r['id']}** ({r['status']}): {r['detail']}" for r in rows + checks
             if r["status"] != "new"]
    md = ["# twin-check board", "",
          f"Run [{run_id}]({run_url}), started {started} UTC, braxtonmensah/twin-check@v1 at `{tc_ref}`.", "",
          "Overlap rates, not score inflation. Twin = a test row whose closest training row has a Levenshtein "
          "ratio of 0.80 or above. Exact = verbatim match. Percent of test rows.", "",
          "## Splits", ""] + md_rows(rows) + [
          "", "## Method checks (reproduce how the record computed two FLIP rows; not sequence measurements)", ""
          ] + md_rows(checks) + ["", "## Cross-check details", ""] + notes + [""]
    with open(os.path.join(out, "BOARD.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(md))

    def html_rows(rs):
        cells = []
        for r in rs:
            src = " ".join(f'<a href="{html.escape(u)}">[{i + 1}]</a>' for i, u in enumerate(r["source_urls"]))
            num = lambda k: f"{r[k]:,}" if isinstance(r.get(k), int) else "n/a"
            pct = lambda k: f"{r[k]}%" if k in r else "n/a"
            cls = {"PASS": "pass", "FAIL": "fail"}.get(r["status"], "other")
            cells.append(
                f"<tr><td>{html.escape(r['benchmark'])}<br><span class=sub>{html.escape(r['split'])}</span></td>"
                f"<td>{src}</td><td><a href=\"{html.escape(r['license_url'])}\">{html.escape(r['license'])}</a></td>"
                f"<td class=n>{num('n_train')}</td><td class=n>{num('n_test')}</td>"
                f"<td class=n><b>{pct('twin_rate_080_pct')}</b></td><td class=n>{pct('exact_rate_pct')}</td>"
                f"<td class={cls} title=\"{html.escape(r['detail'])}\">{html.escape(r['status'])}</td>"
                f"<td><a href=\"{html.escape(r['run_url'])}\">{html.escape(str(r['run_id']))}</a></td></tr>")
        return "\n".join(cells)

    head = ("<tr><th>split</th><th>source</th><th>license</th><th>n_train</th><th>n_test</th>"
            "<th>twin @0.80</th><th>exact</th><th>cross-check</th><th>run</th></tr>")
    page = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>twin-check board</title>
<style>
:root{{--bg:#fff;--fg:#1b1f24;--mut:#57606a;--line:#d0d7de;--pass:#1a7f37;--fail:#cf222e}}
@media (prefers-color-scheme:dark){{:root{{--bg:#0d1117;--fg:#e6edf3;--mut:#8b949e;--line:#30363d;--pass:#3fb950;--fail:#f85149}}}}
body{{background:var(--bg);color:var(--fg);font:15px/1.5 system-ui,sans-serif;margin:0;padding:24px 16px;max-width:1100px;margin:auto}}
a{{color:inherit}} .sub,.mut{{color:var(--mut);font-size:13px}} .wrap{{overflow-x:auto}}
table{{border-collapse:collapse;width:100%;font-size:14px}} th,td{{border-bottom:1px solid var(--line);padding:6px 8px;text-align:left;vertical-align:top}}
td.n{{text-align:right;font-variant-numeric:tabular-nums}} .pass{{color:var(--pass)}} .fail{{color:var(--fail);font-weight:600}}
</style></head><body>
<h1>twin-check board</h1>
<p>Near-twin overlap between published train and test splits, measured weekly in GitHub Actions by
<a href="https://github.com/braxtonmensah/twin-check">braxtonmensah/twin-check@v1</a> (commit <code>{html.escape(tc_ref[:12])}</code>)
as a remote action. Twin: a test row whose closest training row has a Levenshtein ratio of 0.80 or above. Exact: verbatim match. Both are percent of test rows.</p>
<p><b>These are overlap rates, not score inflation.</b> Nothing is retrained here, so a rate does not say how much any reported score is overstated.
No issue was filed on any benchmark by this board. Data is fetched from each benchmark's own URL at run time, checked against a pinned sha256, and not redistributed.</p>
<p class=mut>Run <a href="{html.escape(run_url)}">{html.escape(str(run_id))}</a>, started {html.escape(started)} UTC.
Machine-readable: <a href="board.json">board.json</a>. Source and how to add a split: <a href="https://github.com/braxtonmensah/twin-check-board">github.com/braxtonmensah/twin-check-board</a>.</p>
<h2>Splits</h2><div class=wrap><table>{head}
{html_rows(rows)}
</table></div>
<h2>Method checks</h2>
<p class=mut>These two rows reproduce how Silicyte's published record computed its FLIP conservation and secondary_structure values: on the per-residue label strings in <code>sampled.fasta</code>, not on amino-acid sequences. They are shown so the difference is checkable; the sequence measurements are the rows above.</p>
<div class=wrap><table>{head}
{html_rows(checks)}
</table></div>
<p class=mut>Hover a cross-check cell for its detail. PASS: equal to the live record at
<a href="{html.escape(cfg['record_url'])}">leakage-measurements.json</a> to two decimals (and n where the record lists it). new: not in the record.</p>
</body></html>
"""
    with open(os.path.join(out, "index.html"), "w", encoding="utf-8") as fh:
        fh.write(page)
    fails = [r["id"] for r in rows + checks if r["status"] == "FAIL"]
    with open(os.path.join(out, "status.json"), "w", encoding="utf-8") as fh:
        json.dump({"fails": fails, "n_rows": len(rows), "n_checks": len(checks)}, fh)
    print("\n".join(md))
    gs = os.environ.get("GITHUB_STEP_SUMMARY")
    if gs:
        with open(gs, "a", encoding="utf-8") as fh:
            fh.write("\n".join(md) + "\n")


if __name__ == "__main__":
    main()
