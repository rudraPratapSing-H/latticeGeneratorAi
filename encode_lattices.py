#!/usr/bin/env python3
"""
encode_lattices.py  -  turn labelled lattices into the paper VAE's 48-number shape codes.

Put this file in the repo root (next to the folders fwdTrain, models, results, data) and run:
  python encode_lattices.py --labels C:\\AI-manthan\\data\\model\\strength-labels\\labels_100k_x3.csv

It uses the cached files that validation.py already created in data\\ (train_adj.npz, train_ptb.npz),
so it does NOT rebuild the 17 GB dense arrays. Output: encoded_codes.npz with
  ids (N), mu (N x 48 shape codes), c_paper (N x 9: the paper predictor's stiffness at density 0.15)
It also prints R2 of c_paper against stiffness-vec.csv as a self-check (expect about 98 to 99.5 %).
"""
import argparse, os, sys, time, types
import numpy as np
import pandas as pd
import scipy.sparse as sp
import torch

HERE = os.path.dirname(os.path.abspath(__file__))
ap = argparse.ArgumentParser()
ap.add_argument("--labels", required=True, help="merged labels CSV (needs an 'id' column)")
ap.add_argument("--data-dir", default=os.path.join(HERE, "data"))
ap.add_argument("--results", default=os.path.join(HERE, "results"))
ap.add_argument("--out", default=os.path.join(HERE, "encoded_codes.npz"))
ap.add_argument("--batch", type=int, default=4096)
a = ap.parse_args()

device = "cuda:0" if torch.cuda.is_available() else "cpu"
sd = torch.load(os.path.join(a.results, "best_model.pt"), map_location="cpu")
csd = torch.load(os.path.join(a.results, "best_c_model.pt"), map_location="cpu")
ptb_vec_dim = sd["en_x_fc1.weight"].shape[1]       # sizes read from the trained weights themselves
adj_vec_dim = sd["en_adj_fc1.weight"].shape[1]
print(f"weights loaded: adjacency inputs {adj_vec_dim}, offset inputs {ptb_vec_dim}, device {device}")

# models/model.py does 'from models.parameters import *'. Importing the real parameters.py would load the whole
# dataset as dense arrays (17 GB), so we supply only the constants the model needs.
P = types.ModuleType("models.parameters")
P.__dict__.update(dict(
    ax_dim=32, a_dim=8, x_dim=8, latent_dim=48, z_dim=48,
    c_hidden_dim=[48, 400, 800, 1000, 400, 400, 200], paramDim=9,
    adj_vec_dim=adj_vec_dim, ptb_vec_dim=ptb_vec_dim, device=device))
sys.modules["models.parameters"] = P
sys.path.insert(0, HERE)
from models.model import vaeModel, cModel          # noqa: E402

model = vaeModel().to(device); model.load_state_dict(sd); model.eval()
c_model = cModel().to(device); c_model.load_state_dict(csd); c_model.eval()

ids = np.sort(pd.read_csv(a.labels, usecols=["id"])["id"].astype(int).unique())
print(f"encoding {len(ids)} lattices")
A = sp.load_npz(os.path.join(a.data_dir, "train_adj.npz")).tocsr()
X = sp.load_npz(os.path.join(a.data_dir, "train_ptb.npz")).tocsr()
assert A.shape[1] == adj_vec_dim and X.shape[1] == ptb_vec_dim, (A.shape, X.shape)

mu_all, c_all, t0 = [], [], time.time()
with torch.no_grad():
    for s in range(0, len(ids), a.batch):
        b = ids[s:s + a.batch]
        adj = torch.from_numpy(A[b].toarray()).float().to(device)
        x = torch.from_numpy(X[b].toarray()).float().to(device)
        _, mu, _ = model.encoder(adj, x)
        mu_all.append(mu.cpu().numpy()); c_all.append(c_model(mu).cpu().numpy())
        if (s // a.batch) % 5 == 0:
            print(f"  {min(s + a.batch, len(ids))}/{len(ids)}  {time.time() - t0:.0f}s", flush=True)
mu = np.vstack(mu_all).astype(np.float32); c_paper = np.vstack(c_all).astype(np.float32)

S = pd.read_csv(os.path.join(a.data_dir, "stiffness-vec.csv"), header=None).values[ids]
names = ["C11", "C12", "C13", "C22", "C23", "C33", "C44", "C55", "C66"]
r2 = 1 - ((c_paper - S) ** 2).sum(0) / ((S - S.mean(0)) ** 2).sum(0)
print("self-check, paper predictor vs stiffness-vec.csv (R2 %): " + ", ".join(f"{n} {100 * v:.2f}" for n, v in zip(names, r2)))
np.savez_compressed(a.out, ids=ids.astype(np.int32), mu=mu, c_paper=c_paper)
print(f"wrote {a.out}  codes {mu.shape}")

