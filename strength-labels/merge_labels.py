#!/usr/bin/env python3
"""Merge labels_part*.csv into one file, check it, and report problems.
Usage: python merge_labels.py [folder] [--out labels_100k_x3.csv] [--glob "labels_new_part*.csv"] [--add labels_100k_x3.csv]
  --glob  pattern of the part files to read (default labels_part*.csv)
  --add   an already-merged CSV to include as well (e.g. the earlier 100k file)"""
import glob, os, sys
import numpy as np
import pandas as pd

folder = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("--") else "."
out = sys.argv[sys.argv.index("--out") + 1] if "--out" in sys.argv else "labels_merged.csv"
pat = sys.argv[sys.argv.index("--glob") + 1] if "--glob" in sys.argv else "labels_part*.csv"
add = sys.argv[sys.argv.index("--add") + 1] if "--add" in sys.argv else None
files = sorted(glob.glob(os.path.join(folder, pat)), key=lambda f: int(''.join(c for c in os.path.basename(f) if c.isdigit()) or 0))
assert files, f"no files match {pat} in {folder}"
frames = [pd.read_csv(f) for f in files]
if add:
    frames.append(pd.read_csv(add))
d = pd.concat(frames, ignore_index=True)
print(f"files {len(files)}, rows {len(d)}, lattices {d['id'].nunique()}, densities {sorted(d['rho'].unique())}")
bad = d[d["ok"] != 1]
print(f"failed rows (ok != 1): {len(bad)}")
dup = d.duplicated(["id", "rho"]).sum()
print(f"duplicate (id, rho) rows: {dup}")
d = d[d["ok"] == 1].drop_duplicates(["id", "rho"]).sort_values(["id", "rho"])
cols = [c for c in d.columns if c.startswith(("C", "y_", "b_"))]
print(f"NaN or inf values: {int((~np.isfinite(d[cols].values)).sum())}")
print(f"non-positive strength labels: {int((d[['y_x','y_y','y_z','b_x','b_y','b_z']] <= 0).sum().sum())}")
per = d.groupby("id").size()
print(f"lattices without all densities: {int((per != d['rho'].nunique()).sum())}")
print(d.groupby("rho")[["C1111", "C3333", "y_z", "b_z"]].median().round(5))
d.to_csv(out, index=False)
print(f"wrote {out}: {len(d)} rows")

