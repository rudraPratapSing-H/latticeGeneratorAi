#!/usr/bin/env python3
"""
search_design.py - turn a target (stiffness, strength, weight) into solver-verified lattice designs.

Pipeline (Flow B in the plan)
  1. START   score every stored lattice code with the density-aware predictor, keep the K best as starting points
  2. STEER   gradient descent on the 48-number code (and on the density, if weight is only a limit) so the
             PREDICTED stiffness and strength move toward the target. The decoder is not involved here.
  3. DECODE  decode each final code into a lattice (27 nodes + edges), threshold, keep the largest connected part
  4. VERIFY  the physics solver (lattice_strength.py) recomputes stiffness and strength; density is refined with
             the solver on a small grid, because density is the cheap knob
  5. RANK    keep designs that satisfy each target's mode, order by error then weight

Run from the repo root (next to encode_lattices.py and train_predictor.py), for example:
  python search_design.py --predictor q1.pt --labels C:\\AI-manthan\\data\\model\\strength-labels\\labels_300k_x3.csv ^
      --E-gpa 114 --yield-mpa 880 --density-g-cc 4.43 ^
      --stiffness 8 8 12 --strength 90 90 130 --max-mass-g 60 --part-mm 40 40 40
  python search_design.py --predictor q1.pt --labels ...labels_300k_x3.csv --roundtrip 100      # does the search work?

Material numbers are YOUR inputs (E in GPa, yield in MPa, density in g/cm3); no material table is built in.
Strength used in the search = min(yield_strength, buckling_strength) per axis, as decided in the plan.
The predictor was trained at relative densities 0.05, 0.15 and 0.25, so the density is kept inside --rho-min/--rho-max.
"""
import argparse, hashlib, json, os, sys, time, types
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
for _p in (os.environ.get("SOLVER_DIR"), os.path.join(HERE, "..", "strength-labels"), os.path.join(HERE, "strength-labels")):
    if _p and os.path.exists(os.path.join(_p, "lattice_strength.py")):
        sys.path.insert(0, _p)
        break

def _is_t(x):
    return type(x).__module__.startswith("torch")


def _log(x):
    if _is_t(x):
        import torch
        return torch.log(x)
    return np.log(np.maximum(x, 1e-12))


def _pos(x):
    if _is_t(x):
        import torch
        return torch.clamp(x, min=0)
    return np.maximum(x, 0)


ALLOWED_MODES = {"stiffness": ("about", "at_least", "at_most"),
                 "strength": ("about", "at_least", "at_most"),
                 "weight": ("at_most", "about")}
AX = ["x", "y", "z"]


# ------------------------------------------------------------------ loading
def load_models(results_dir, data_dir, device):
    """VAE (encoder+decoder) and the paper's stiffness head, with sizes read from the checkpoint."""
    import torch
    sd = torch.load(os.path.join(results_dir, "best_model.pt"), map_location="cpu")
    csd = torch.load(os.path.join(results_dir, "best_c_model.pt"), map_location="cpu")
    ptb_vec_dim, adj_vec_dim = sd["en_x_fc1.weight"].shape[1], sd["en_adj_fc1.weight"].shape[1]
    P = types.ModuleType("models.parameters")
    P.__dict__.update(dict(ax_dim=32, a_dim=8, x_dim=8, latent_dim=48, z_dim=48,
                           c_hidden_dim=[48, 400, 800, 1000, 400, 400, 200], paramDim=9,
                           adj_vec_dim=adj_vec_dim, ptb_vec_dim=ptb_vec_dim, device=device))
    sys.modules["models.parameters"] = P
    from models.model import vaeModel, cModel
    vae = vaeModel().to(device); vae.load_state_dict(sd); vae.eval()
    cmod = cModel().to(device); cmod.load_state_dict(csd); cmod.eval()
    for p in list(vae.parameters()) + list(cmod.parameters()):
        p.requires_grad_(False)
    mask = np.loadtxt(os.path.join(data_dir, "ptb_mask.csv"), delimiter=",")
    return vae, cmod, mask


def load_predictor(path, device):
    import torch, torch.nn as nn
    ck = torch.load(path, map_location="cpu", weights_only=False)
    if ck.get("raw", False):
        raise SystemExit("this predictor reads raw adjacency/offset vectors, so it cannot steer the 48-number code. "
                         "Use a predictor trained without --raw.")
    sdict = ck["state_dict"]
    n_in, H = sdict["0.weight"].shape[1], sdict["0.weight"].shape[0]
    drop = ck.get("dropout", 0.0) > 0
    layers = [nn.Linear(n_in, H), nn.ReLU()] + ([nn.Dropout(ck["dropout"])] if drop else [])
    for _ in range(ck["layers"] - 1):
        layers += [nn.Linear(H, H), nn.ReLU()] + ([nn.Dropout(ck["dropout"])] if drop else [])
    net = nn.Sequential(*layers, nn.Linear(H, 15))
    net.load_state_dict(sdict); net.eval().to(device)
    for p in net.parameters():
        p.requires_grad_(False)
    T = lambda a: torch.tensor(np.asarray(a), dtype=torch.float32, device=device)
    return dict(net=net, x_mean=T(ck["x_mean"]), x_std=T(ck["x_std"]), y_mean=T(ck["y_mean"]), y_std=T(ck["y_std"]),
                paper=bool(ck.get("paper_stiffness", False)))


# ------------------------------------------------------------------ predictor in torch (differentiable)
def predict(pred, cmod, z, rho):
    """z: (B,48) code, rho: (B,) relative density -> stiffness C9 (B,9) (units of E_s), yield (B,3), buckling (B,3)."""
    import torch
    parts = [z, ((rho - 0.15) / 0.1)[:, None], torch.log(rho / 0.15)[:, None]]
    if pred["paper"]:
        parts.append(cmod(z))
    X = (torch.cat(parts, 1) - pred["x_mean"]) / pred["x_std"]
    T = pred["net"](X) * pred["y_std"] + pred["y_mean"]
    C9 = T[:, :9] * rho[:, None]
    return C9, torch.exp(T[:, 9:12]), torch.exp(T[:, 12:15])


def c9_to_E(C9):
    """Young's moduli along x, y, z from the 9 stiffness entries (orthotropic 6x6, batched, differentiable)."""
    import torch
    B = C9.shape[0]
    C = torch.zeros(B, 6, 6, dtype=C9.dtype, device=C9.device)
    C[:, 0, 0], C[:, 0, 1], C[:, 0, 2] = C9[:, 0], C9[:, 1], C9[:, 2]
    C[:, 1, 0], C[:, 1, 1], C[:, 1, 2] = C9[:, 1], C9[:, 3], C9[:, 4]
    C[:, 2, 0], C[:, 2, 1], C[:, 2, 2] = C9[:, 2], C9[:, 4], C9[:, 5]
    C[:, 3, 3], C[:, 4, 4], C[:, 5, 5] = C9[:, 6], C9[:, 7], C9[:, 8]
    S = torch.linalg.inv(C + 1e-9 * torch.eye(6, dtype=C9.dtype, device=C9.device))
    return 1.0 / torch.stack([S[:, 0, 0], S[:, 1, 1], S[:, 2, 2]], 1)


# ------------------------------------------------------------------ targets and loss
class Target:
    """Normalised targets. Stiffness is E / E_s. Strength is expressed in units of the yield stress:
    effective = min(y, r * b) with r = E_s / sigma_y, where y and b are the solver's yield and buckling labels."""

    def __init__(self, mat, stiffness_gpa=None, strength_mpa=None, yield_mpa=None, rho=None, rho_max=None,
                 modes=None, tol=0.10):
        self.mat, self.tol = mat, tol
        self.r = mat["E_gpa"] * 1000.0 / mat["yield_mpa"]            # E_s / sigma_y (both in MPa)
        self.modes = {"stiffness": "about", "strength": "at_least", "weight": "at_most"}
        self.modes.update(modes or {})
        for k, v in self.modes.items():
            assert v in ALLOWED_MODES[k], f"mode {v} not allowed for {k}"
        self.E = None if stiffness_gpa is None else np.array([np.nan if v is None else v / mat["E_gpa"] for v in stiffness_gpa])
        self.yield_only = yield_mpa is not None
        s = yield_mpa if self.yield_only else strength_mpa
        self.S = None if s is None else np.array([np.nan if v is None else v / mat["yield_mpa"] for v in s])
        self.rho = rho                  # fixed density, or None when weight is only a limit
        self.rho_max = rho_max

    def effective(self, y, b):
        """strength in units of sigma_y from the yield and buckling labels (works for numpy and torch)."""
        if self.yield_only:
            return y
        if _is_t(y):
            import torch
            return torch.minimum(y, self.r * b)
        return np.minimum(y, self.r * b)

    def terms(self, E, S):
        """per-axis log errors (torch or numpy). Ignored axes (NaN targets) are skipped.
        'about': log(pred/target); 'at_least': only the shortfall; 'at_most': only the excess."""
        out = []
        for pred, tgt, mode in ((E, self.E, self.modes["stiffness"]), (S, self.S, self.modes["strength"])):
            if tgt is None:
                continue
            for a in range(3):
                if np.isnan(tgt[a]):
                    continue
                e = _log(pred[:, a] / float(tgt[a]))                # > 0: prediction above target
                if mode == "at_least":
                    e = _pos(-e)
                elif mode == "at_most":
                    e = _pos(e)
                out.append(e)
        return out


def search_loss(tg, E, S):
    terms = tg.terms(E, S)
    return sum(t ** 2 for t in terms)


# ------------------------------------------------------------------ decode and repair
def node_positions(ptb27, nodes_init=None):
    """Offsets (27,3) -> node positions in [0,1]^3, using the paper's ptb2nodes."""
    from models.utils import ptb2nodes
    return ptb2nodes(ptb27)


def largest_component(adj):
    """keep only the biggest connected set of nodes that have edges."""
    from scipy.sparse.csgraph import connected_components
    from scipy.sparse import csr_matrix
    deg = adj.sum(1) > 0
    if not deg.any():
        return adj
    n, lab = connected_components(csr_matrix(adj), directed=False)
    sizes = np.bincount(lab[deg], minlength=n)
    keep = (lab == sizes.argmax()) & deg
    out = adj.copy()
    out[~keep, :] = 0
    out[:, ~keep] = 0
    return out


MIN_STRUT = 1e-3        # shortest strut kept, in octant units (cell side is 2)


def decode_codes(vae, z, mask, device):
    """latent codes (B,48) -> list of (adj 27x27 0/1 symmetric, positions 27x3)."""
    import torch
    x_row, x_col = np.nonzero(mask)
    a_row, a_col = np.triu_indices(27)
    with torch.no_grad():
        adj_p, x_p = vae.decoder(z.to(device))
    adj_p, x_p = adj_p.cpu().numpy(), x_p.cpu().numpy()
    res = []
    for i in range(len(z)):
        tri = np.zeros((27, 27))
        tri[a_row, a_col] = (adj_p[i] > 0.5).astype(float)
        adj = ((tri + tri.T) > 0).astype(float)
        np.fill_diagonal(adj, 0)
        ptb = np.zeros((27, 3))
        xv = np.clip(x_p[i], -0.5, 0.5)
        xv[np.abs(xv) < 1e-3] = 0.0
        ptb[x_row, x_col] = xv
        pos = node_positions(ptb)
        # a strut between two nodes at (almost) the same point has no length: the solver divides by zero. drop it.
        dist = np.linalg.norm(pos[:, None, :] - pos[None, :, :], axis=-1)
        adj[dist < MIN_STRUT] = 0
        res.append((largest_component(adj), pos))
    return res


# ------------------------------------------------------------------ solver
def solve(adj, pos, rho):
    import lattice_strength as ls
    with np.errstate(all="ignore"):
        r = ls.solve_lattice(adj, pos, rho=rho)
        C = r["C"]
        S = np.linalg.inv(C)
        E = 1.0 / np.diag(S)[:3]
    out = dict(E=E, y=np.asarray(r["y"]), b=np.asarray(r["b"]), r_cell=float(r["r"]), n_struts=int(r["n_struts"]))
    for k in ("E", "y", "b"):                      # a broken solve (zero-length strut, singular matrix) is not a design
        if not np.all(np.isfinite(out[k])) or np.any(out[k] <= 0):
            raise ValueError("solver returned non-finite or non-positive " + k)
    return out


def solver_loss(tg, res):
    E = res["E"][None]
    S = tg.effective(res["y"], res["b"])[None]
    return float(search_loss(tg, E, S)[0])


def solver_errors(tg, res):
    """relative error per active target in the sense of its mode (0 if an at_least / at_most limit is met),
    and the threshold each must stay under to count as a match."""
    E = res["E"]; S = tg.effective(res["y"], res["b"])
    errs, thr = [], []
    for pred, tgt, mode in ((E, tg.E, tg.modes["stiffness"]), (S, tg.S, tg.modes["strength"])):
        if tgt is None:
            continue
        for a in range(3):
            if np.isnan(tgt[a]):
                continue
            rel = pred[a] / tgt[a] - 1.0
            if mode == "about":
                errs.append(abs(rel)); thr.append(tg.tol)
            elif mode == "at_least":
                errs.append(max(-rel, 0.0)); thr.append(0.005)
            else:
                errs.append(max(rel, 0.0)); thr.append(0.005)
    return np.array(errs), np.array(thr)


# ------------------------------------------------------------------ the search
def run_search(vae, cmod, pred, mask, codes, tg, device, K=100, steps=100, lr=0.002, noise=0.0, rho_lo=0.05,
               rho_hi=0.25, n_grid=9, light=0.02, seed=0, use_gradient=True, random_start=False, workers=1,
               pool_idx=None, log=print, cache=None):
    """returns a list of candidate dicts sorted best first. `cache` (a dict) remembers solver results between calls."""
    import torch
    if cache is None:
        cache = {}
    g = torch.Generator(device="cpu").manual_seed(seed)
    mu = torch.tensor(codes, dtype=torch.float32, device=device)
    if pool_idx is not None:
        mu = mu[torch.as_tensor(pool_idx, device=device)]
    rho_fixed = tg.rho
    hi = min(rho_hi, tg.rho_max if tg.rho_max else rho_hi)
    lo = min(rho_lo, hi)
    free_density = rho_fixed is None

    # ---- 1. starting points: score stored codes at a few densities, keep the K best ----
    t0 = time.time()
    grid = [rho_fixed] if not free_density else list(np.unique(np.clip(np.array([0.05, 0.10, 0.15, 0.20, 0.25]), lo, hi)))
    if free_density and (hi not in grid):
        grid.append(hi)
    best_l = torch.full((len(mu),), float("inf"), device=device)
    best_r = torch.zeros(len(mu), device=device)
    with torch.no_grad():
        for rr in grid:
            for s in range(0, len(mu), 50000):
                z = mu[s:s + 50000]
                rho = torch.full((len(z),), float(rr), device=device)
                C9, y, b = predict(pred, cmod, z, rho)
                E = c9_to_E(C9)
                S = tg.effective(y, b)
                l = search_loss(tg, E, S)
                better = l < best_l[s:s + 50000]
                best_l[s:s + 50000] = torch.where(better, l, best_l[s:s + 50000])
                best_r[s:s + 50000] = torch.where(better, rho, best_r[s:s + 50000])
    if random_start:
        idx = torch.randperm(len(mu), generator=g)[:K].to(device)
    else:
        idx = torch.argsort(best_l)[:K]
    z0, r0 = mu[idx].clone(), best_r[idx].clone()
    log(f"  start: scored {len(mu)} stored codes, best predicted loss {best_l[idx[0]].item():.4f} "
        f"({time.time() - t0:.1f}s)")

    # ---- 2. steer the code (and density) by gradient descent on the predictor ----
    z = (z0 + noise * torch.randn(z0.shape, generator=g).to(device)).requires_grad_(True)
    lo_z, hi_z = mu.min(0).values, mu.max(0).values
    span = hi_z - lo_z
    lo_z, hi_z = lo_z - 0.1 * span, hi_z + 0.1 * span                  # stay near the region the model has seen
    u = torch.logit(((r0 - lo) / max(hi - lo, 1e-9)).clamp(0.02, 0.98)).clone().requires_grad_(free_density)
    params = [z] + ([u] if free_density else [])
    if use_gradient and steps > 0:
        opt = torch.optim.Adam(params, lr=lr)
        best_z, best_u, best_loss = z.detach().clone(), u.detach().clone(), torch.full((K,), float("inf"), device=device)
        start_z, start_u = z.detach().clone(), u.detach().clone()      # the unsteered starting points
        snap_at, snap_z, snap_u = max(steps // 3, 1), None, None       # and one early snapshot of the walk
        for it in range(steps):
            rho = lo + (hi - lo) * torch.sigmoid(u) if free_density else torch.full((K,), float(rho_fixed), device=device)
            C9, y, b = predict(pred, cmod, z, rho)
            E = c9_to_E(C9)
            l_each = search_loss(tg, E, tg.effective(y, b)) + (light * (rho / hi) if free_density else 0.0)
            loss = l_each.sum()
            opt.zero_grad(); loss.backward(); opt.step()
            with torch.no_grad():
                z.copy_(torch.max(torch.min(z, hi_z), lo_z))
                imp = l_each.detach() < best_loss
                best_loss = torch.where(imp, l_each.detach(), best_loss)
                best_z[imp] = z.detach()[imp]
                best_u[imp] = u.detach()[imp]
                if it + 1 == snap_at:
                    snap_z, snap_u = z.detach().clone(), u.detach().clone()
        # the predictor's own optimum is optimistic (steering finds where the predictor is wrong in our favour), and the
        # solver is the judge. so send the solver the starts and an early snapshot as well as the steered end points.
        parts_z, parts_u = [start_z, snap_z, best_z], [start_u, snap_u, best_u]
        z_fin = torch.cat([p for p in parts_z if p is not None])
        u_fin = torch.cat([p for p in parts_u if p is not None])
        origins = sum([[nm] * len(p) for nm, p in zip(("start", "early", "steered"), parts_z) if p is not None], [])
        log(f"  steer: {steps} steps, best predicted loss {best_loss.min().item():.4f}, "
            f"median {best_loss.median().item():.4f}")
    else:
        z_fin, u_fin = z.detach(), u.detach()
        origins = ["start"] * len(z_fin)
    rho_fin = (lo + (hi - lo) * torch.sigmoid(u_fin)) if free_density else torch.full((len(z_fin),), float(rho_fixed), device=device)

    # ---- 3. decode ----
    t1 = time.time()
    lat = decode_codes(vae, z_fin, mask, device)
    log(f"  decode: {len(lat)} lattices ({time.time() - t1:.1f}s)")

    # ---- 4. verify with the solver; refine density on a small grid when weight is only a limit ----
    seen, cands, bad = set(), [], 0
    for i, (adj, pos) in enumerate(lat):
        if adj.sum() == 0:
            bad += 1
            continue
        key = hashlib.md5(adj.astype(np.int8).tobytes() + np.round(pos, 3).tobytes()).hexdigest()
        if key in seen:
            continue
        seen.add(key)
        rhos = [float(rho_fixed)] if not free_density else \
            sorted(set(np.round(np.exp(np.linspace(np.log(lo), np.log(hi), n_grid)).tolist() + [float(rho_fin[i])], 5)))
        best = None
        for rr in rhos:
            ck = (key, rr)
            if ck not in cache:
                try:
                    cache[ck] = solve(adj, pos, rr)
                except Exception:
                    cache[ck] = None
            res = cache[ck]
            if res is None or not np.all(np.isfinite(res["E"])) or np.any(res["y"] <= 0):
                continue
            l = solver_loss(tg, res) + (light * rr / hi if free_density else 0.0)
            if best is None or l < best[0]:
                best = (l, rr, res)
        if best is None:
            bad += 1
            continue
        l, rr, res = best
        errs, thr = solver_errors(tg, res)
        cands.append(dict(adj=adj, pos=pos, rho=rr, res=res, loss=l, max_err=float(errs.max()) if len(errs) else 0.0,
                          match=bool(np.all(errs <= thr)), z=z_fin[i].cpu().numpy(), origin=origins[i]))
    log(f"  verify: {len(cands)} distinct valid lattices, {bad} failed or empty ({time.time() - t1:.1f}s incl. decode)")

    # ---- 5. rank, and add what the predictor thought (for the predicted-vs-verified display) ----
    cands.sort(key=lambda c: (not c["match"], c["max_err"], c["rho"]))
    # different codes often decode to lattices with the same verified behaviour; show each behaviour once
    kept, sigs = [], []
    for c in cands:
        sig = np.log(np.concatenate([c["res"]["E"], tg.effective(c["res"]["y"], c["res"]["b"])]))
        if any(c["rho"] == k["rho"] and np.max(np.abs(sig - s0)) < 0.01 for k, s0 in zip(kept, sigs)):
            continue
        kept.append(c); sigs.append(sig)
    cands = kept
    if cands:
        with torch.no_grad():
            zc = torch.tensor(np.stack([c["z"] for c in cands]), dtype=torch.float32, device=device)
            rc = torch.tensor([c["rho"] for c in cands], dtype=torch.float32, device=device)
            C9, y, b = predict(pred, cmod, zc, rc)
            E = c9_to_E(C9).cpu().numpy(); y = y.cpu().numpy(); b = b.cpu().numpy()
        for k, c in enumerate(cands):
            c["pred"] = dict(E=E[k], y=y[k], b=b[k])
    return cands



def search_adaptive(vae, cmod, pred, mask, codes, tg, device, ladder=(100, 300, 1000), time_budget=60.0,
                    min_gain=0.005, infeasible=False, on_round=None, log=None, **kw):
    """start with few starting points; if no design meets every target, search again with more.
    stops when a design matches, when a round gains less than `min_gain` (0.005 = half a point of worst-axis error),
    when the next round would exceed the time budget, or at the end of the ladder. solver results are reused between rounds.
    returns (candidates, history); `on_round(history_row, candidates)` is called after every round (for progress display)."""
    cache, history, best, t0 = {}, [], None, time.time()
    steps_ = list(ladder)[:1] if infeasible else list(ladder)
    for r, K in enumerate(steps_):
        t1 = time.time()
        if log:
            log(f"  [round {r + 1}: K={K}]")
        cands = run_search(vae, cmod, pred, mask, codes, tg, device, K=K, cache=cache, log=log or (lambda *_: None), **kw)
        err = cands[0]["max_err"] if cands else float("inf")
        gain = (best[0] - err) if best is not None else float("inf")
        if best is None or err < best[0]:
            best = (err, cands)
        row = dict(round=r + 1, K=K, best_err=err, matched=bool(cands and cands[0]["match"]), n_candidates=len(cands),
                   round_seconds=time.time() - t1, elapsed_seconds=time.time() - t0)
        history.append(row)
        if on_round:
            on_round(row, best[1])
        if row["matched"]:
            break
        if r + 1 < len(steps_):
            if gain < min_gain and r > 0:
                break
            per_start = (time.time() - t1) / K
            if (time.time() - t0) + per_start * steps_[r + 1] > time_budget:
                break
    return best[1], history


# ------------------------------------------------------------------ output
def to_candidate_json(c, tg, rank, cell_mm, part_mm):
    res, rho = c["res"], c["rho"]
    nodes = np.round(c["pos"], 6)
    a, b = np.where(np.triu(c["adj"], 1) > 0)
    edges = [[int(i), int(j)] for i, j in zip(a, b)]
    P = c["pred"]
    E_mpa = tg.mat["E_gpa"] * 1000
    out = dict(
        id="d_" + hashlib.md5(c["adj"].astype(np.int8).tobytes() + np.round(c["pos"], 3).tobytes()).hexdigest()[:8], rank=rank, match_error_pct=round(100 * c["max_err"], 2),
        matches_targets=bool(c["match"]), rel_density=round(rho, 5),
        lattice=dict(format="octant27", nodes=nodes.tolist(), edges=edges, cell_size_mm=cell_mm,
                     strut_radius_mm=round(res["r_cell"] * cell_mm / 2.0, 5)),
        predicted=dict(stiffness_gpa=dict(zip(AX, (P["E"] * tg.mat["E_gpa"]).round(4).tolist())),
                       yield_strength_mpa=dict(zip(AX, (P["y"] * tg.mat["yield_mpa"]).round(3).tolist())),
                       buckling_strength_mpa=dict(zip(AX, (P["b"] * E_mpa).round(3).tolist())),
                       strength_mpa=dict(zip(AX, np.minimum(P["y"] * tg.mat["yield_mpa"], P["b"] * E_mpa).round(3).tolist()))),
        verified=dict(stiffness_gpa=dict(zip(AX, (res["E"] * tg.mat["E_gpa"]).round(4).tolist())),
                      yield_strength_mpa=dict(zip(AX, (res["y"] * tg.mat["yield_mpa"]).round(3).tolist())),
                      buckling_strength_mpa=dict(zip(AX, (res["b"] * tg.mat["E_gpa"] * 1000).round(3).tolist())),
                      strength_mpa=dict(zip(AX, np.minimum(res["y"] * tg.mat["yield_mpa"],
                                                           res["b"] * tg.mat["E_gpa"] * 1000).round(3).tolist()))))
    out["verified"]["governing_failure"] = {k: ("yield" if y * tg.mat["yield_mpa"] <= b * tg.mat["E_gpa"] * 1000 else "buckling")
                                            for k, y, b in zip(AX, res["y"], res["b"])}
    if part_mm:
        vol_cm3 = float(np.prod(part_mm)) / 1000.0
        out["mass_g"] = round(rho * vol_cm3 * tg.mat["density_g_cc"], 3)
    return out


def print_table(cands, tg, n=5):
    print(f"\n{'rank':>4} {'match':>5} {'err%':>6} {'rho':>6} | {'E_x':>7} {'E_y':>7} {'E_z':>7} (GPa) | "
          f"{'S_x':>7} {'S_y':>7} {'S_z':>7} (MPa)")
    for k, c in enumerate(cands[:n], 1):
        r = c["res"]
        E = r["E"] * tg.mat["E_gpa"]
        S = np.minimum(r["y"] * tg.mat["yield_mpa"], r["b"] * tg.mat["E_gpa"] * 1000)
        print(f"{k:>4} {'yes' if c['match'] else 'no':>5} {100 * c['max_err']:6.1f} {c['rho']:6.3f} | "
              f"{E[0]:7.2f} {E[1]:7.2f} {E[2]:7.2f}       | {S[0]:7.1f} {S[1]:7.1f} {S[2]:7.1f}")


# ------------------------------------------------------------------ round-trip test
def roundtrip(a, vae, cmod, pred, mask, codes_npz, mat, device):
    """Targets come from solver values of lattices the predictor never saw; can the search find a design for them?"""
    import pandas as pd
    from train_predictor import split_ids
    d = pd.read_csv(a.labels)
    d = d[d["ok"] == 1].reset_index(drop=True)
    ids_u = codes_npz["ids"]
    tr_ids, va_ids, te_ids = split_ids(d["id"].values, 0)
    pool_idx = np.where(np.isin(ids_u, tr_ids))[0]                     # starts come from TRAINING lattices only
    rng = np.random.default_rng(a.seed)
    te = d[d["id"].isin(te_ids)]
    pick = te.iloc[rng.choice(len(te), min(a.roundtrip, len(te)), replace=False)]
    near_R = float(getattr(a, "exclude_near", 0) or 0)
    n_excl = []
    if near_R > 0:
        # true six values (E x,y,z and effective strength x,y,z, in solver units) of every TRAINING lattice at each density
        dd = d[d["id"].isin(tr_ids)]
        N = np.zeros((len(dd), 3, 3))
        for (i, j), col in {(0, 0): "C1111", (0, 1): "C1122", (0, 2): "C1133", (1, 1): "C2222", (1, 2): "C2233", (2, 2): "C3333"}.items():
            N[:, i, j] = N[:, j, i] = dd[col].values
        with np.errstate(all="ignore"):
            E_tr = 1.0 / np.diagonal(np.linalg.inv(N), axis1=1, axis2=2)
        r_ = mat["E_gpa"] * 1000.0 / mat["yield_mpa"]
        S_tr = np.minimum(dd[["y_x", "y_y", "y_z"]].values, r_ * dd[["b_x", "b_y", "b_z"]].values)
        vals_tr, rho_tr, id_tr = np.hstack([E_tr, S_tr]), dd["rho"].values, dd["id"].values
        print(f"exclusion test: for each target, stored lattices with all six values within {100 * near_R:.0f}% of it are removed from the pool")
    variants = [("full search", dict(use_gradient=True)), ("scored starts only (no steering)", dict(use_gradient=False)),
                ("random starts + steering", dict(use_gradient=True, random_start=True))]
    if a.variants == "full":
        variants = variants[:1]
    rows = {v: [] for v, _ in variants}
    for n, (_, row) in enumerate(pick.iterrows(), 1):
        rho = float(row["rho"])
        C = np.array([[row["C1111"], row["C1122"], row["C1133"], 0, 0, 0], [row["C1122"], row["C2222"], row["C2233"], 0, 0, 0],
                      [row["C1133"], row["C2233"], row["C3333"], 0, 0, 0], [0, 0, 0, row["C2323"], 0, 0],
                      [0, 0, 0, 0, row["C3131"], 0], [0, 0, 0, 0, 0, row["C1212"]]])
        E = 1.0 / np.diag(np.linalg.inv(C))[:3]
        y = row[["y_x", "y_y", "y_z"]].values.astype(float)
        b = row[["b_x", "b_y", "b_z"]].values.astype(float)
        r = mat["E_gpa"] * 1000.0 / mat["yield_mpa"]
        S_eff = np.minimum(y, r * b)
        tg = Target(mat, stiffness_gpa=(E * mat["E_gpa"]).tolist(), strength_mpa=(S_eff * mat["yield_mpa"]).tolist(),
                    rho=rho, modes=dict(stiffness="about", strength="about"), tol=a.tol)
        pool_t = pool_idx
        if near_R > 0:
            sel = np.where(np.isclose(rho_tr, rho))[0]
            with np.errstate(all="ignore"):
                dev = np.abs(vals_tr[sel] / np.concatenate([E, S_eff]) - 1.0).max(1)
            near_ids = id_tr[sel][dev < near_R]
            pool_t = pool_idx[~np.isin(ids_u[pool_idx], near_ids)]
            n_excl.append(len(pool_idx) - len(pool_t))
        for vname, kw in variants:
            cs = run_search(vae, cmod, pred, mask, codes_npz["mu"], tg, device, K=a.K, steps=a.steps, lr=a.lr,
                            noise=a.noise, seed=a.seed + n, pool_idx=pool_t, log=lambda *_: None, **kw)
            rows[vname].append(cs[0]["max_err"] if cs else np.nan)
        if n % 10 == 0:
            print(f"  {n}/{len(pick)} targets done", flush=True)
    print(f"\nROUND-TRIP: {len(pick)} unseen lattices, all 6 targets (E and strength per axis) must be within {100 * a.tol:.0f}%")
    if near_R > 0:
        print(f"EXCLUSION: stored lattices within {100 * near_R:.0f}% on all six values were removed from the pool "
              f"(median {np.median(n_excl):.0f}, min {min(n_excl)}, max {max(n_excl)} of {len(pool_idx)} removed per target)")
    print(f"{'variant':<36}{'success':>9}{'median err %':>14}{'90th pct err %':>16}")
    for vname, _ in variants:
        e = np.array(rows[vname], dtype=float)
        ok = np.nanmean(e <= a.tol)
        print(f"{vname:<36}{100 * ok:8.0f}%{100 * np.nanmedian(e):14.1f}{100 * np.nanpercentile(e, 90):16.1f}")



# ------------------------------------------------------------------ diagnosis
def diagnose(a, vae, cmod, pred, mask, codes_npz, mat, device):
    """Why does a search miss? Uses the same unseen-lattice targets as --roundtrip, runs the full search once per target
    and reports (1) which of the 6 properties miss, (2) which stage the best design came from, (3) how far the predictor
    is from the solver at each stage."""
    import pandas as pd
    from train_predictor import split_ids
    d = pd.read_csv(a.labels)
    d = d[d["ok"] == 1].reset_index(drop=True)
    ids_u = codes_npz["ids"]
    tr_ids, va_ids, te_ids = split_ids(d["id"].values, 0)
    pool_idx = np.where(np.isin(ids_u, tr_ids))[0]
    rng = np.random.default_rng(a.seed)
    te = d[d["id"].isin(te_ids)]
    pick = te.iloc[rng.choice(len(te), min(a.diagnose, len(te)), replace=False)]
    names = ["E_x", "E_y", "E_z", "S_x", "S_y", "S_z"]
    axis_err = []                                   # best design: |verified / target - 1| per property
    best_origin, best_by_origin = [], {o: [] for o in ("start", "early", "steered")}
    trust = {o: [] for o in ("start", "early", "steered")}   # |predicted / verified - 1|, pooled over the 6 properties
    n_cands = []
    for n, (_, row) in enumerate(pick.iterrows(), 1):
        rho = float(row["rho"])
        C = np.array([[row["C1111"], row["C1122"], row["C1133"], 0, 0, 0], [row["C1122"], row["C2222"], row["C2233"], 0, 0, 0],
                      [row["C1133"], row["C2233"], row["C3333"], 0, 0, 0], [0, 0, 0, row["C2323"], 0, 0],
                      [0, 0, 0, 0, row["C3131"], 0], [0, 0, 0, 0, 0, row["C1212"]]])
        E = 1.0 / np.diag(np.linalg.inv(C))[:3]
        y = row[["y_x", "y_y", "y_z"]].values.astype(float)
        b = row[["b_x", "b_y", "b_z"]].values.astype(float)
        r = mat["E_gpa"] * 1000.0 / mat["yield_mpa"]
        S_eff = np.minimum(y, r * b)
        tg = Target(mat, stiffness_gpa=(E * mat["E_gpa"]).tolist(), strength_mpa=(S_eff * mat["yield_mpa"]).tolist(),
                    rho=rho, modes=dict(stiffness="about", strength="about"), tol=a.tol)
        cs = run_search(vae, cmod, pred, mask, codes_npz["mu"], tg, device, K=a.K, steps=a.steps, lr=a.lr,
                        noise=a.noise, seed=a.seed + n, pool_idx=pool_idx, log=lambda *_: None)
        n_cands.append(len(cs))
        if not cs:
            continue
        tgt = np.concatenate([tg.E, tg.S])
        for c in cs:
            ver = np.concatenate([c["res"]["E"], tg.effective(c["res"]["y"], c["res"]["b"])])
            prd = np.concatenate([c["pred"]["E"], tg.effective(c["pred"]["y"], c["pred"]["b"])])
            c["_ver_err"] = np.abs(ver / tgt - 1.0)
            trust[c["origin"]].extend(np.abs(prd / ver - 1.0).tolist())
        top = cs[0]
        axis_err.append(top["_ver_err"])
        best_origin.append(top["origin"])
        for o in best_by_origin:
            e = [c["_ver_err"].max() for c in cs if c["origin"] == o]
            best_by_origin[o].append(min(e) if e else np.nan)
        if n % 5 == 0:
            print(f"  {n}/{len(pick)} targets done", flush=True)

    axis_err = np.array(axis_err)
    print(f"\nDIAGNOSIS on {len(axis_err)} unseen targets (median {np.median(n_cands):.0f} distinct verified lattices per target)")
    print("\n1. Which property misses? (best design found, error vs target)")
    print(f"{'property':<10}{'median err %':>14}{'share > tol %':>16}")
    for k, nm in enumerate(names):
        print(f"{nm:<10}{100 * np.median(axis_err[:, k]):14.1f}{100 * np.mean(axis_err[:, k] > a.tol):16.0f}")
    print("\n2. Where did the best design come from?")
    for o in ("start", "early", "steered"):
        print(f"  {o:<8}{100 * np.mean([x == o for x in best_origin]):5.0f}% of targets")
    print("\n3. Best worst-axis error reachable from each stage alone (and how often it is within tolerance)")
    print(f"{'stage':<10}{'median err %':>14}{'success %':>12}")
    for o, v in best_by_origin.items():
        v = np.array(v, dtype=float)
        print(f"{o:<10}{100 * np.nanmedian(v):14.1f}{100 * np.nanmean(v <= a.tol):12.0f}")
    print("\n4. Predictor vs solver on the decoded lattices (median |predicted / verified - 1|, all six properties)")
    for o, v in trust.items():
        v = np.array(v, dtype=float)
        ok = v[np.isfinite(v)]
        if len(ok):
            print(f"  {o:<8}{100 * np.median(ok):6.1f}%   (n={len(ok)}, {len(v) - len(ok)} non-finite skipped)")
    print("\nReading it: if error in 4 grows from start to steered, steering exploits predictor mistakes. If it is already large at"
          " start, the decoder or predictor is the limit. If one property in 1 dominates, target that one.")


# ------------------------------------------------------------------ main
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--predictor", required=True, help="trained predictor, e.g. q1.pt (trained WITHOUT --raw)")
    ap.add_argument("--labels", help="labels CSV (only needed for --roundtrip)")
    ap.add_argument("--codes", default=os.path.join(HERE, "encoded_codes.npz"))
    ap.add_argument("--results", default=os.path.join(HERE, "results"))
    ap.add_argument("--data-dir", default=os.path.join(HERE, "data"))
    ap.add_argument("--out", default="search_results.json")
    # material (your numbers)
    ap.add_argument("--E-gpa", type=float, required=True, help="base material Young's modulus, GPa")
    ap.add_argument("--yield-mpa", type=float, required=True, help="base material yield stress, MPa")
    ap.add_argument("--density-g-cc", type=float, default=1.0, help="base material density, g/cm3 (for mass)")
    # targets
    ap.add_argument("--stiffness", type=float, nargs=3, metavar=("X", "Y", "Z"), help="target Young's modulus per axis, GPa")
    ap.add_argument("--strength", type=float, nargs=3, metavar=("X", "Y", "Z"), help="target strength per axis, MPa (min of yield and buckling)")
    ap.add_argument("--yield-strength", type=float, nargs=3, metavar=("X", "Y", "Z"), help="target first-yield strength per axis, MPa (instead of --strength)")
    ap.add_argument("--rel-density", type=float, help="fixed relative density")
    ap.add_argument("--max-mass-g", type=float, help="weight limit in grams (needs --part-mm)")
    ap.add_argument("--part-mm", type=float, nargs=3, metavar=("X", "Y", "Z"), help="part size in mm")
    ap.add_argument("--cell-mm", type=float, default=10.0)
    ap.add_argument("--mode-stiffness", default="about", choices=ALLOWED_MODES["stiffness"])
    ap.add_argument("--mode-strength", default="at_least", choices=ALLOWED_MODES["strength"])
    ap.add_argument("--mode-weight", default="at_most", choices=ALLOWED_MODES["weight"])
    ap.add_argument("--tol", type=float, default=0.10, help="tolerance for 'about' targets (0.10 = 10%%)")
    ap.add_argument("--n-results", type=int, default=5)
    # search settings
    ap.add_argument("--K", type=int, default=100, help="number of starting points (30 -> 75%%, 100 -> 90%%, 300 -> 90%% on 20 round-trip targets)")
    ap.add_argument("--steps", type=int, default=100, help="steering steps; steps x lr (total movement) of about 0.2 worked best, 0.4 broke the predictor")
    ap.add_argument("--lr", type=float, default=0.002)
    ap.add_argument("--noise", type=float, default=0.0, help="random noise added to the starting codes")
    ap.add_argument("--rho-min", type=float, default=0.05)
    ap.add_argument("--rho-max", type=float, default=0.25)
    ap.add_argument("--seed", type=int, default=0)
    # round-trip test
    ap.add_argument("--roundtrip", type=int, default=0, help="run the round-trip test on this many unseen lattices")
    ap.add_argument("--exclude-near", type=float, default=0.0,
                    help="round-trip: remove stored lattices whose six true values are all within this fraction of the target "
                         "(0.15 = 15%%), to test targets that have no near match in the dataset")
    ap.add_argument("--from-test-lattice", type=int, default=None, metavar="N",
                    help="take the request (six numbers + density) from the Nth held-out lattice, so a design is known to exist")
    ap.add_argument("--unseen-from", default=None, metavar="LABELS_CSV",
                    help="with --from-test-lattice: draw the request only from lattices NOT in this labels file (the ones the predictor was trained on), "
                         "e.g. labels_100k_x3.csv, so the request is a lattice the predictor has never seen")
    ap.add_argument("--ladder", type=int, nargs="+", default=[100, 300, 1000],
                    help="single search: numbers of starting points to try in turn until a design matches")
    ap.add_argument("--time-budget", type=float, default=60.0, help="single search: stop escalating after about this many seconds")
    ap.add_argument("--verbose", action="store_true", help="single search: print the time of each stage")
    ap.add_argument("--no-adaptive", action="store_true", help="single search: use --K once, no escalation")
    ap.add_argument("--diagnose", type=int, default=0, help="explain misses on this many unseen lattices (needs --labels)")
    ap.add_argument("--variants", default="all", choices=["all", "full"], help="round-trip: compare against baselines")
    a = ap.parse_args()

    import torch
    device = "cuda:0" if torch.cuda.is_available() else "cpu"
    mat = dict(E_gpa=a.E_gpa, yield_mpa=a.yield_mpa, density_g_cc=a.density_g_cc)
    print(f"device {device}; material E={a.E_gpa} GPa, yield={a.yield_mpa} MPa, density={a.density_g_cc} g/cm3 "
          f"(E/yield = {a.E_gpa * 1000 / a.yield_mpa:.0f})")
    vae, cmod, mask = load_models(a.results, a.data_dir, device)
    pred = load_predictor(a.predictor, device)
    z = np.load(a.codes)
    print(f"loaded {len(z['ids'])} stored lattice codes")

    if a.diagnose:
        assert a.labels, "--diagnose needs --labels"
        diagnose(a, vae, cmod, pred, mask, z, mat, device)
        return
    if a.roundtrip:
        assert a.labels, "--roundtrip needs --labels"
        roundtrip(a, vae, cmod, pred, mask, z, mat, device)
        return

    pool_idx = None
    if a.from_test_lattice is not None:
        assert a.labels, "--from-test-lattice needs --labels"
        import pandas as pd
        from train_predictor import split_ids
        dl = pd.read_csv(a.labels)
        dl = dl[dl["ok"] == 1].reset_index(drop=True)
        tr_ids, _, te_ids = split_ids(dl["id"].values, 0)
        te = dl[dl["id"].isin(te_ids)].sample(frac=1.0, random_state=0)   # shuffled, so #N is a random held-out lattice
        if a.unseen_from:
            seen = np.unique(pd.read_csv(a.unseen_from, usecols=["id"])["id"].values)
            te = dl[~dl["id"].isin(seen)].sample(frac=1.0, random_state=0)
            tr_ids = np.setdiff1d(dl["id"].unique(), te["id"].values)   # pool = only the lattices the predictor was built from
            print(f"requests are drawn from {te['id'].nunique()} lattices the predictor never trained on")
        row = te.iloc[a.from_test_lattice % len(te)]
        Cm = np.array([[row["C1111"], row["C1122"], row["C1133"]], [row["C1122"], row["C2222"], row["C2233"]],
                       [row["C1133"], row["C2233"], row["C3333"]]])
        E_t = 1.0 / np.diag(np.linalg.inv(Cm))
        S_t = np.minimum(row[["y_x", "y_y", "y_z"]].values.astype(float),
                         (a.E_gpa * 1000.0 / a.yield_mpa) * row[["b_x", "b_y", "b_z"]].values.astype(float))
        a.stiffness = (E_t * a.E_gpa).round(3).tolist()
        a.strength = (S_t * a.yield_mpa).round(2).tolist()
        a.rel_density = float(row["rho"])
        pool_idx = np.where(np.isin(z["ids"], tr_ids))[0]          # the lattice itself is not in the pool
        if a.exclude_near > 0:
            # also remove every training lattice whose six true values are all within this fraction of the request
            dd = dl[dl["id"].isin(tr_ids) & np.isclose(dl["rho"], a.rel_density)]
            N = np.zeros((len(dd), 3, 3))
            for (i, j), col in {(0, 0): "C1111", (0, 1): "C1122", (0, 2): "C1133", (1, 1): "C2222", (1, 2): "C2233", (2, 2): "C3333"}.items():
                N[:, i, j] = N[:, j, i] = dd[col].values
            with np.errstate(all="ignore"):
                E_tr = 1.0 / np.diagonal(np.linalg.inv(N), axis1=1, axis2=2)
            S_tr = np.minimum(dd[["y_x", "y_y", "y_z"]].values,
                              (a.E_gpa * 1000.0 / a.yield_mpa) * dd[["b_x", "b_y", "b_z"]].values)
            tgt6 = np.concatenate([E_t, S_t])
            dev = np.abs(np.hstack([E_tr, S_tr]) / tgt6 - 1.0).max(1)
            near_ids = dd["id"].values[dev < a.exclude_near]
            n_before = len(pool_idx)
            pool_idx = pool_idx[~np.isin(z["ids"][pool_idx], near_ids)]
            print(f"exclusion: removed {n_before - len(pool_idx)} stored lattices within {100 * a.exclude_near:.0f}% of the request on all six values")
        print(f"request taken from held-out lattice #{a.from_test_lattice}: stiffness {a.stiffness} GPa, "
              f"strength {a.strength} MPa, relative density {a.rel_density} (a design is known to exist)")
    assert a.stiffness or a.strength or a.yield_strength, "give at least one of --stiffness / --strength / --yield-strength"
    rho_fixed, rho_max = a.rel_density, None
    if a.max_mass_g:
        assert a.part_mm, "--max-mass-g needs --part-mm"
        vol_cm3 = float(np.prod(a.part_mm)) / 1000.0
        rho_lim = a.max_mass_g / (vol_cm3 * a.density_g_cc)
        print(f"weight limit -> relative density at most {rho_lim:.3f}")
        if rho_lim < a.rho_min:
            print(f"WARNING: limit is below the trained density range ({a.rho_min}); results will be extrapolated")
        if a.mode_weight == "about":
            rho_fixed = rho_lim
        else:
            rho_max = rho_lim
    tg = Target(mat, stiffness_gpa=a.stiffness, strength_mpa=a.strength, yield_mpa=a.yield_strength, rho=rho_fixed,
                rho_max=rho_max, modes=dict(stiffness=a.mode_stiffness, strength=a.mode_strength, weight=a.mode_weight),
                tol=a.tol)
    t0 = time.time()
    rho_top = rho_fixed if rho_fixed is not None else (rho_max if rho_max else a.rho_max)
    # the limit is approximate (and a plain cubic lattice sits exactly on it), so allow a 5% margin before calling a request impossible
    infeasible = bool(a.stiffness and None not in a.stiffness and rho_top and sum(a.stiffness) > 1.05 * rho_top * a.E_gpa)
    ladder = [a.K] if a.no_adaptive else a.ladder
    def _show(row, _c):
        print(f"  round {row['round']}: K={row['K']:<5} best worst-axis error {100 * row['best_err']:5.1f}%  "
              f"{'MATCH' if row['matched'] else 'no match yet'}  ({row['elapsed_seconds']:.0f}s)", flush=True)
    cands, history = search_adaptive(vae, cmod, pred, mask, z["mu"], tg, device, ladder=ladder, time_budget=a.time_budget,
                                     infeasible=infeasible, on_round=_show, log=(print if a.verbose else None), steps=a.steps, lr=a.lr, noise=a.noise,
                                     rho_lo=a.rho_min, rho_hi=a.rho_max, seed=a.seed, pool_idx=pool_idx)
    print(f"\n{len(cands)} candidates in {time.time() - t0:.0f}s; {sum(c['match'] for c in cands)} satisfy every target")
    print_table(cands, tg, a.n_results)
    if infeasible:
        print(f"\nWARNING: the three stiffness targets add up to {sum(a.stiffness):.1f} GPa, but at relative density "
              f"{rho_top:.3f} no lattice of this material can exceed about {rho_top * a.E_gpa:.1f} GPa in total "
              f"(density x E). This request cannot be met; the designs below are the closest found.")
    elif cands and not cands[0]["match"]:
        print(f"\nNOTE: no design meets every target; the closest is off by {100 * cands[0]['max_err']:.0f}% on its worst property.")
    js = [to_candidate_json(c, tg, k, a.cell_mm, a.part_mm) for k, c in enumerate(cands[:a.n_results], 1)]
    with open(a.out, "w") as f:
        json.dump(dict(material=mat, rounds=history, infeasible=infeasible, candidates=js), f, indent=1)
    print(f"\nwrote {a.out}")


if __name__ == "__main__":
    main()
