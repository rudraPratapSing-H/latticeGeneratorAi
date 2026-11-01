#!/usr/bin/env python3
"""
train_predictor.py - train the density-aware stiffness + strength predictor on the paper VAE's shape codes.

Inputs : encoded_codes.npz (from encode_lattices.py) and the merged labels CSV (labels_100k_x3.csv)
Model  : fully connected, 50 inputs (48-number shape code + 2 density features) -> 15 outputs
         (9 stiffness, 3 yield, 3 buckling), 3 hidden layers of 256, ReLU.
Targets: stiffness / rho (so the main density trend is removed), log of the strength labels; all standardised.
Split  : 80/10/10 by LATTICE id (all densities of a lattice stay together).
Run    : python train_predictor.py --codes encoded_codes.npz --labels labels_100k_x3.csv
Output : predictor.pt (weights + scalers), metrics_test.csv (printed too).
"""
import argparse, json, os, time
import numpy as np
import pandas as pd

STIFF = ["C1111", "C1122", "C1133", "C2222", "C2233", "C3333", "C2323", "C3131", "C1212"]
STR = ["y_x", "y_y", "y_z", "b_x", "b_y", "b_z"]
NAMES = STIFF + STR
# the paper weights coupling terms 80, shear 30, axial 15; divided by 15 here because targets are standardised
WEIGHTS = np.array([1, 5.33, 5.33, 1, 5.33, 1, 2, 2, 2] + [1] * 6, dtype=np.float32)


def load_table(labels_csv, codes_npz):
    d = pd.read_csv(labels_csv)
    d = d[d["ok"] == 1].reset_index(drop=True)
    z = np.load(codes_npz)
    ids, mu = z["ids"], z["mu"]
    pos = np.searchsorted(ids, d["id"].values)
    assert (pos < len(ids)).all() and (ids[pos] == d["id"].values).all(), "labels contain ids missing from the codes"
    cp = z["c_paper"][pos].astype(np.float32) if "c_paper" in z.files else None
    return d, mu[pos].astype(np.float32), cp


def features(mu, rho, c_paper=None):
    parts = [mu, ((rho - 0.15) / 0.1)[:, None], np.log(rho / 0.15)[:, None]]
    if c_paper is not None:            # the paper predictor's stiffness at density 0.15 (very accurate, R2 98 to 99.5 %)
        parts.append(c_paper)
    return np.hstack(parts).astype(np.float32)


def to_targets(d):
    rho = d["rho"].values[:, None]
    return np.hstack([d[STIFF].values / rho, np.log(d[STR].values)]).astype(np.float32)


def to_physical(T, rho):
    rho = np.asarray(rho)[:, None]
    return np.hstack([T[:, :9] * rho, np.exp(T[:, 9:])])


def split_ids(ids, seed=0):
    u = np.unique(ids)
    p = np.random.default_rng(seed).permutation(u)
    n = len(u)
    return p[: int(0.8 * n)], p[int(0.8 * n): int(0.9 * n)], p[int(0.9 * n):]


def metrics(pred, true, rho):
    """pred, true: physical units, shape (n, 15). Returns a DataFrame."""
    rows = []
    for j, name in enumerate(NAMES):
        p, t = pred[:, j], true[:, j]
        if j >= 9:                      # strength spans orders of magnitude: R2 on the log scale
            r2 = 1 - ((np.log(p) - np.log(t)) ** 2).sum() / ((np.log(t) - np.log(t).mean()) ** 2).sum()
        else:
            r2 = 1 - ((p - t) ** 2).sum() / ((t - t.mean()) ** 2).sum()
        rel = np.abs(p - t) / np.maximum(np.abs(t), 1e-12)
        row = {"output": name, "R2_%": 100 * r2, "median_rel_err_%": 100 * np.median(rel)}
        for r in np.unique(rho):
            row[f"rel_err_%@{r:.2f}"] = 100 * np.median(rel[np.isclose(rho, r)])
        rows.append(row)
    return pd.DataFrame(rows)


def baseline_mean_at_density(true_tr, rho_tr, rho_te):
    out = np.zeros((len(rho_te), true_tr.shape[1]))
    for r in np.unique(rho_te):
        out[np.isclose(rho_te, r)] = np.median(true_tr[np.isclose(rho_tr, r)], axis=0)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--codes", default="encoded_codes.npz")
    ap.add_argument("--labels", required=True)
    ap.add_argument("--out", default="predictor.pt")
    ap.add_argument("--epochs", type=int, default=200)
    ap.add_argument("--batch", type=int, default=512)
    ap.add_argument("--lr", type=float, default=1e-3)
    ap.add_argument("--patience", type=int, default=20)
    ap.add_argument("--hidden", type=int, default=256)
    ap.add_argument("--layers", type=int, default=3, help="number of hidden layers")
    ap.add_argument("--paper-stiffness", action="store_true",
                    help="also feed the paper predictor's stiffness (from encoded_codes.npz) as 9 extra inputs")
    ap.add_argument("--dropout", type=float, default=0.0, help="dropout probability after each hidden layer (0 = off)")
    ap.add_argument("--weight-decay", type=float, default=0.0, help="AdamW weight decay (0 = off)")
    ap.add_argument("--raw", action="store_true",
                    help="DIAGNOSTIC: use the raw adjacency+offset vectors (405 numbers) instead of the 48-number code")
    ap.add_argument("--data-dir", default="data", help="folder with train_adj.npz and train_ptb.npz (used with --raw)")
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args()

    d, mu, cp = load_table(a.labels, a.codes)
    if a.paper_stiffness:
        assert cp is not None, "encoded_codes.npz has no c_paper"
        print("using the paper predictor's stiffness as extra inputs")
    rho = d["rho"].values
    tr_ids, va_ids, te_ids = split_ids(d["id"].values, a.seed)
    sel = lambda ids: np.isin(d["id"].values, ids)
    m_tr, m_va, m_te = sel(tr_ids), sel(va_ids), sel(te_ids)
    print(f"rows: train {m_tr.sum()}, val {m_va.sum()}, test {m_te.sum()}  (lattices {len(tr_ids)}/{len(va_ids)}/{len(te_ids)})")

    shape_in = mu
    if a.raw:
        import scipy.sparse as sp
        A = sp.load_npz(os.path.join(a.data_dir, "train_adj.npz")).tocsr()
        Xp = sp.load_npz(os.path.join(a.data_dir, "train_ptb.npz")).tocsr()
        ids_row = d["id"].values.astype(int)
        shape_in = np.hstack([A[ids_row].toarray(), Xp[ids_row].toarray()]).astype(np.float32)
        print(f"RAW INPUT MODE: {shape_in.shape[1]} raw numbers per lattice instead of the 48-number code")
    X, T = features(shape_in, rho, cp if a.paper_stiffness else None), to_targets(d)
    x_mean = X[m_tr].mean(0)
    x_std = np.maximum(X[m_tr].std(0), 0.1 if a.raw else 1e-6)   # floor stops rare 0/1 columns blowing up
    y_mean, y_std = T[m_tr].mean(0), T[m_tr].std(0) + 1e-9
    Xn, Yn = (X - x_mean) / x_std, (T - y_mean) / y_std

    import torch, torch.nn as nn
    torch.manual_seed(a.seed)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    H = a.hidden
    drop = (lambda: [nn.Dropout(a.dropout)]) if a.dropout > 0 else (lambda: [])
    layers = [nn.Linear(X.shape[1], H), nn.ReLU()] + drop()
    for _ in range(a.layers - 1):
        layers += [nn.Linear(H, H), nn.ReLU()] + drop()
    net = nn.Sequential(*layers, nn.Linear(H, 15)).to(device)
    print(f"network: {a.layers} hidden layers of {H}, {sum(p.numel() for p in net.parameters())} parameters")
    w = torch.tensor(WEIGHTS, device=device)
    opt = torch.optim.AdamW(net.parameters(), lr=a.lr, weight_decay=a.weight_decay)
    sched = torch.optim.lr_scheduler.StepLR(opt, step_size=20, gamma=0.5)
    tx = lambda m: torch.from_numpy(Xn[m]).to(device)
    ty = lambda m: torch.from_numpy(Yn[m]).to(device)
    Xtr, Ytr, Xva, Yva = tx(m_tr), ty(m_tr), tx(m_va), ty(m_va)

    best, best_state, bad, t0 = 1e18, None, 0, time.time()
    for ep in range(a.epochs):
        net.train()
        perm = torch.randperm(len(Xtr), device=device)
        tl, nb = 0.0, 0
        for s in range(0, len(perm), a.batch):
            b = perm[s:s + a.batch]
            loss = (((net(Xtr[b]) - Ytr[b]) ** 2) * w).mean()
            opt.zero_grad(); loss.backward(); opt.step()
            tl += loss.item(); nb += 1
        sched.step()
        net.eval()
        with torch.no_grad():
            vl = (((net(Xva) - Yva) ** 2) * w).mean().item()
        if vl < best - 1e-6:
            best, bad = vl, 0
            best_state = {k: v.detach().cpu().clone() for k, v in net.state_dict().items()}
        else:
            bad += 1
        if ep % 5 == 0 or bad == 0:
            print(f"epoch {ep + 1:3d}  train loss {tl / nb:.5f}  val loss {vl:.5f}  best {best:.5f}  {time.time() - t0:.0f}s", flush=True)
        if bad >= a.patience:
            print(f"early stop at epoch {ep + 1}")
            break

    net.load_state_dict(best_state); net.eval()
    with torch.no_grad():
        pn = net(tx(m_te)).cpu().numpy()
    pred = to_physical(pn * y_std + y_mean, rho[m_te])
    true = to_physical(T[m_te], rho[m_te])
    print("\nTEST SET (lattices the predictor never saw)")
    res = metrics(pred, true, rho[m_te])
    print(res.round(2).to_string(index=False))
    with torch.no_grad():
        pn_tr = net(Xtr).cpu().numpy()
    pred_tr = to_physical(pn_tr * y_std + y_mean, rho[m_tr])
    true_tr = to_physical(T[m_tr], rho[m_tr])
    res_tr = metrics(pred_tr, true_tr, rho[m_tr])
    cmp_ = pd.DataFrame({"output": res["output"], "train_R2_%": res_tr["R2_%"], "test_R2_%": res["R2_%"]})
    cmp_["gap"] = cmp_["train_R2_%"] - cmp_["test_R2_%"]
    print("\nOVERFITTING CHECK (gap = train R2 minus test R2; a big gap means more data would help)")
    print(cmp_.round(2).to_string(index=False))
    base = baseline_mean_at_density(to_physical(T[m_tr], rho[m_tr]), rho[m_tr], rho[m_te])
    bres = metrics(base, true, rho[m_te])
    print("\nBASELINE (ignores the shape; predicts the typical value at that density)")
    print(bres[["output", "R2_%", "median_rel_err_%"]].round(2).to_string(index=False))
    mfile = os.path.splitext(a.out)[0] + "_metrics.csv"
    cmp_.merge(res, on="output").to_csv(mfile, index=False)
    torch.save({"state_dict": best_state, "x_mean": x_mean, "x_std": x_std, "y_mean": y_mean, "y_std": y_std,
                "hidden": H, "layers": a.layers, "raw": a.raw, "dropout": a.dropout, "paper_stiffness": a.paper_stiffness, "names": NAMES, "weights": WEIGHTS}, a.out)
    print(f"\nsaved {a.out} and {mfile}")


if __name__ == "__main__":
    main()

