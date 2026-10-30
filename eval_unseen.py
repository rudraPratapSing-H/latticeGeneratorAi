"""Test a trained predictor on lattices that were NOT in the 100k it trained on.
Usage: python eval_unseen.py --predictor q1.pt --codes encoded_codes.npz ^
         --trained-labels ..\\strength-labels\\labels_100k_x3.csv --labels ..\\strength-labels\\labels_300k_x3.csv
Compares: (a) its own held-out test split, (b) the other lattices in --labels that are not in --trained-labels."""
import argparse, numpy as np, pandas as pd, torch
from train_predictor import load_table, features, to_targets, to_physical, metrics, split_ids, NAMES

ap = argparse.ArgumentParser()
ap.add_argument("--predictor", required=True); ap.add_argument("--codes", required=True)
ap.add_argument("--trained-labels", required=True); ap.add_argument("--labels", required=True)
a = ap.parse_args()

ck = torch.load(a.predictor, map_location="cpu", weights_only=False)
assert not ck.get("raw", False), "raw predictors need the adjacency files; use a 48-number predictor"
sd = ck["state_dict"]; H = sd["0.weight"].shape[0]; n_in = sd["0.weight"].shape[1]
dr = [torch.nn.Dropout(ck["dropout"])] if ck.get("dropout", 0.0) > 0 else []
L = [torch.nn.Linear(n_in, H), torch.nn.ReLU()] + dr
for _ in range(ck["layers"] - 1):
    L += [torch.nn.Linear(H, H), torch.nn.ReLU()] + dr
net = torch.nn.Sequential(*L, torch.nn.Linear(H, 15)); net.load_state_dict(sd); net.eval()

def run(d, mu, cp):
    X = features(mu, d["rho"].values, cp if ck.get("paper_stiffness") else None)
    Xn = (X - ck["x_mean"]) / ck["x_std"]
    with torch.no_grad():
        out = net(torch.from_numpy(Xn.astype(np.float32))).numpy()
    return to_physical(out * ck["y_std"] + ck["y_mean"], d["rho"].values), to_physical(to_targets(d), d["rho"].values)

dt, _, _ = load_table(a.trained_labels, a.codes)
trained = np.unique(dt["id"].values)
_, _, te_ids = split_ids(dt["id"].values, 0)
d, mu, cp = load_table(a.labels, a.codes)
for name, m in (("A. its own held-out test lattices (never trained on)", np.isin(d["id"].values, te_ids)),
                ("B. lattices OUTSIDE the 100k it was built from", ~np.isin(d["id"].values, trained))):
    p, t = run(d[m], mu[m], cp[m] if cp is not None else None)
    r = metrics(p, t, d["rho"].values[m])
    print(f"\n{name}: {len(np.unique(d['id'].values[m]))} lattices, {m.sum()} rows")
    print(r.round(2).to_string(index=False))
    # how often is each lattice's worst error under 10 %
    rel = np.abs(p - t) / np.maximum(np.abs(t), 1e-12)
    print(f"stiffness (3 axial) all within 10%: {100*np.mean(rel[:, [0,3,5]].max(1) < .1):.1f}%   "
          f"all 9 stiffness: {100*np.mean(rel[:, :9].max(1) < .1):.1f}%   yield+buckling (6) all within 10%: {100*np.mean(rel[:, 9:].max(1) < .1):.1f}%")
