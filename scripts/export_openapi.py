"""Write the backend's OpenAPI document for the frontend type generator (run by `npm run gen:api` in lattice-web)."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from server.app import app  # noqa: E402

out = ROOT / "lattice-web" / "src" / "api" / "openapi.json"
out.write_text(json.dumps(app.openapi(), indent=1), encoding="utf-8")
print(f"wrote {out}")
