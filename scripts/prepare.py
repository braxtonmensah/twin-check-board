"""Fetch one split's public files from their official URLs, check each sha256 (and md5 where pinned),
and write train/test FASTA for braxtonmensah/twin-check. Runs only on GitHub Actions runners.

usage: python -I scripts/prepare.py <split-id> <outdir>

Writes <outdir>/train.fasta, <outdir>/test.fasta and <outdir>/meta.json, and appends
train=, test= to $GITHUB_OUTPUT. Nothing downloaded here is committed anywhere.
"""
import csv
import gzip
import hashlib
import io
import json
import os
import pickle
import re
import sys
import time
import urllib.request
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
csv.field_size_limit(1 << 30)


def load_spec(split_id):
    cfg = json.load(open(os.path.join(ROOT, "splits.json"), encoding="utf-8"))
    for s in cfg["splits"] + cfg.get("method_checks", []):
        if s["id"] == split_id:
            return s
    raise SystemExit(f"unknown split id {split_id}")


def fetch(url, tries=4):
    last = None
    for k in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "twin-check-board/1.0"})
            with urllib.request.urlopen(req, timeout=600) as r:
                return r.read()
        except Exception as exc:  # network flake on a shared runner
            last = exc
            time.sleep(10 * (k + 1))
    raise SystemExit(f"download failed after {tries} tries: {url}: {last}")


def get(spec, name, hashes):
    data = fetch(spec["url"])
    sha = hashlib.sha256(data).hexdigest()
    md5 = hashlib.md5(data).hexdigest()
    ok = sha == spec["sha256"] and ("md5" not in spec or md5 == spec["md5"])
    print(f"{name}: {len(data)} bytes sha256 {sha} md5 {md5} {'OK' if ok else 'MISMATCH'}")
    if not ok:
        raise SystemExit(f"checksum mismatch for {name} ({spec['url']}): pinned sha256 {spec['sha256']}")
    hashes[name] = {"url": spec["url"], "sha256": sha, "md5": md5, "bytes": len(data)}
    return data


def read_fasta(text):
    """Return [(header, sequence)], joining wrapped lines."""
    out, head, cur = [], None, []
    for line in text.splitlines():
        if line.startswith(">"):
            if head is not None:
                out.append((head, "".join(cur)))
            head, cur = line[1:].strip(), []
        elif line.strip():
            if head is None:
                raise SystemExit("sequence line before the first FASTA header")
            cur.append(line.strip())
    if head is not None:
        out.append((head, "".join(cur)))
    return out


def lrgb_seqs(files, hashes):
    raw = get(files["data"], "data", hashes)
    rows = list(csv.DictReader(io.StringIO(gzip.decompress(raw).decode("utf-8"))))
    return [r["peptide_seq"] for r in rows]


def flip_split_labels(z, member):
    """FLIP FASTA tasks put the split in the defline: '>ID SET=train VALIDATION=False'."""
    recs = read_fasta(z.read(member).decode("utf-8"))
    out = []
    for head, label in recs:
        m = re.search(r"\bSET=(\w+)", head)
        if not m:
            raise SystemExit(f"no SET= in defline: {head!r}")
        out.append((head.split()[0], m.group(1).lower(), label))
    return out


def build(spec, hashes):
    kind, files = spec["kind"], spec["files"]
    if kind == "lrgb_pickle":
        import numpy as np
        seqs = lrgb_seqs(files, hashes)
        sp = pickle.loads(get(files["split"], "split", hashes))
        tr = [seqs[i] for i in np.asarray(sp["train"]).ravel()]
        te = [seqs[i] for i in np.asarray(sp["test"]).ravel()]
    elif kind == "lrgb_json_split":
        seqs = lrgb_seqs(files, hashes)
        sp = json.loads(get(files["split"], "split", hashes))["splits"]
        tr = [seqs[int(i)] for i in sp["train"]]
        te = [seqs[int(i)] for i in sp["test"]]
    elif kind == "fasta_pair":
        tr = [s for _, s in read_fasta(get(files["train"], "train", hashes).decode("utf-8"))]
        te = [s for _, s in read_fasta(get(files["test"], "test", hashes).decode("utf-8"))]
    elif kind == "zip_csv_set":
        z = zipfile.ZipFile(io.BytesIO(get(files["zip"], "zip", hashes)))
        rows = list(csv.DictReader(io.StringIO(z.read(spec["member"]).decode("utf-8"))))
        sets = sorted({r["set"] for r in rows})
        if sets != ["test", "train"]:
            raise SystemExit(f"unexpected set values {sets} in {spec['member']}")
        tr = [r["sequence"] for r in rows if r["set"] == "train"]
        te = [r["sequence"] for r in rows if r["set"] == "test"]
    elif kind in ("flip_fasta_join", "flip_fasta_labels"):
        z = zipfile.ZipFile(io.BytesIO(get(files["zip"], "zip", hashes)))
        lab = flip_split_labels(z, spec["labels_member"])
        sets = sorted({s for _, s, _ in lab})
        if sets != ["test", "train"]:
            raise SystemExit(f"unexpected SET values {sets}")
        if kind == "flip_fasta_labels":
            # The record's script (verify_sweep.py flip_fasta) read these strings as if they were
            # sequences. Reproduced here only to show where the record's number came from.
            tr = [x for _, s, x in lab if s == "train"]
            te = [x for _, s, x in lab if s == "test"]
        else:
            seqrecs = read_fasta(z.read(spec["sequences_member"]).decode("utf-8"))
            ids = [h.split()[0] for h, _ in seqrecs]
            if len(set(ids)) != len(ids):
                raise SystemExit("duplicate ids in sequences file")
            seq = {h.split()[0]: s for h, s in seqrecs}
            missing = [i for i, _, _ in lab if i not in seq]
            if missing:
                raise SystemExit(f"{len(missing)} split ids have no sequence, e.g. {missing[:3]}")
            bad = sum(1 for i, _, x in lab if len(seq[i]) != len(x))
            print(f"joined {len(lab)} split ids to sequences; label/sequence length mismatches: {bad}")
            # Show what each file holds, so the label-vs-sequence distinction is checkable in the log.
            lab_alpha = sorted(set("".join(x for _, _, x in lab)))
            seq_alpha = sorted(set("".join(seq[i] for i, _, _ in lab)))
            print(f"{spec['labels_member']} alphabet ({len(lab_alpha)}): {''.join(lab_alpha)[:40]}")
            print(f"{spec['sequences_member']} alphabet ({len(seq_alpha)}): {''.join(seq_alpha)[:40]}")
            tr = [seq[i] for i, s, _ in lab if s == "train"]
            te = [seq[i] for i, s, _ in lab if s == "test"]
    else:
        raise SystemExit(f"unknown kind {kind}")
    if not tr or not te:
        raise SystemExit("empty train or test")
    return tr, te


def write_fasta(path, seqs):
    with open(path, "w", encoding="utf-8") as fh:
        for i, s in enumerate(seqs):
            fh.write(f">r{i}\n{s}\n")


def main():
    split_id, out = sys.argv[1], sys.argv[2]
    os.makedirs(out, exist_ok=True)
    spec = load_spec(split_id)
    hashes = {}
    tr, te = build(spec, hashes)
    print(f"rows: train {len(tr)} test {len(te)}")
    write_fasta(os.path.join(out, "train.fasta"), tr)
    write_fasta(os.path.join(out, "test.fasta"), te)
    meta = {"id": split_id, "files": hashes, "n_train_rows": len(tr), "n_test_rows": len(te)}
    with open(os.path.join(out, "meta.json"), "w", encoding="utf-8") as fh:
        json.dump(meta, fh, indent=1)
    gh = os.environ.get("GITHUB_OUTPUT")
    if gh:
        with open(gh, "a") as fh:
            fh.write(f"train={out}/train.fasta\ntest={out}/test.fasta\n")


if __name__ == "__main__":
    main()
