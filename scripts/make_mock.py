"""Regenerate the mock files from real search output (never edit mock/ by hand).

    python scripts/make_mock.py [--samples-dir DIR]

1. copies sample_*.json (real search_design.py output) from DIR (default: repo root) into mock/ when found;
2. writes mock/materials.json from server.units.MATERIALS;
3. writes mock/job_done.json: a finished job built from mock/sample_3.json, whose request is known (titanium,
   density 0.05, stiffness 0.465 0.496 0.402 GPa, strength 2.22 2.65 2.19 MPa), run through the same server code
   (picker, mass, warnings) the real pipeline uses.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core import mock  # noqa: E402
from server import finalize, picker, units  # noqa: E402
from server.jobs import rank_candidates  # noqa: E402
from server.schemas import DesignRequest  # noqa: E402

MOCK_DIR = ROOT / "mock"
JOB_ID = "j_mock0001"
SAMPLE_3_REQUEST = {
    "material": "ti64", "part": {"size_mm": [40, 40, 40], "cell_mm": 10},
    "target": {"stiffness_gpa": {"x": 0.465, "y": 0.496, "z": 0.402},
               "strength_mpa": {"x": 2.22, "y": 2.65, "z": 2.19}, "rel_density": 0.05},
    "modes": {"stiffness": "about", "strength": "at_least", "weight": "about"}, "tolerance_pct": 10, "n_results": 5,
}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--samples-dir", type=Path, default=ROOT)
    a = ap.parse_args(argv)
    MOCK_DIR.mkdir(exist_ok=True)
    for f in sorted(a.samples_dir.glob("sample_*.json")):
        shutil.copyfile(f, MOCK_DIR / f.name)
        print("copied", f.name)

    (MOCK_DIR / "materials.json").write_text(json.dumps(list(units.MATERIALS.values()), indent=2), encoding="utf-8")

    sample = json.loads((MOCK_DIR / "sample_3.json").read_text(encoding="utf-8"))
    request = DesignRequest(**SAMPLE_3_REQUEST)
    material = units.MATERIALS[request.material]
    cands = [mock.with_predicted_governing(c) for c in sample["candidates"]]
    top = rank_candidates(cands, request.n_results)
    top = finalize.finalize_candidates(top, JOB_ID, request, material, list(request.part.size_mm), request.part.cell_mm)
    reach = picker.reach_for_request(request, material)
    job = {
        "job_id": JOB_ID, "status": "done", "stage": "rank", "round": len(sample["rounds"]),
        "k": sample["rounds"][-1]["K"], "progress": 1.0,
        "message": f"Found {sum(c['matches_targets'] for c in top)} design(s) meeting every target.",
        "queue_position": None, "rounds": finalize.rounds_info(sample["rounds"]), "infeasible": sample["infeasible"],
        "warnings": list(reach.get("warnings", [])), "reach": {k: reach[k] for k in ("level", "distance_pct", "density")},
        "candidates": top, "request": request.model_dump(mode="json"),
    }
    (MOCK_DIR / "job_done.json").write_text(json.dumps(finalize.sanitize(job), indent=2, allow_nan=False),
                                            encoding="utf-8")
    print("wrote mock/materials.json and mock/job_done.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
