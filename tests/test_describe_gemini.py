"""T17: Gemini description parsing with a mocked HTTP layer (no key, no network), and the offline fallback."""
import json
import sys
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts.make_test_stem import make_stem  # noqa: E402
from server import describe_service  # noqa: E402
from server.app import app  # noqa: E402

TEXT = "Hip stem for a 82 kg patient who walks daily. Keep the neck solid."


def answer(obj):
    return {"candidates": [{"content": {"parts": [{"text": json.dumps(obj)}]}}]}


def mock(monkeypatch, handler):
    monkeypatch.setattr(describe_service, "_client", lambda: httpx.Client(transport=httpx.MockTransport(handler), timeout=5))


def test_without_a_key_the_offline_rules_are_used(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    mock(monkeypatch, lambda r: pytest.fail("no request may be made without a key"))
    out = describe_service.parse(TEXT)
    assert out["parsed_by"] == "offline" and out["body_weight_kg"] == 82 and not describe_service.gemini_enabled()


def test_gemini_answer_is_used_and_sent_with_the_key_in_a_header_only(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key-123")
    monkeypatch.setenv("GEMINI_MODEL", "gemini-test")
    seen = {}

    def handler(request: httpx.Request):
        seen["url"], seen["key"], seen["body"] = str(request.url), request.headers.get("x-goog-api-key"), json.loads(request.content)
        return httpx.Response(200, json=answer({"implant_type": "hip stem", "body_weight_kg": 82, "activity": "moderate",
                                                "special_rules": ["Keep the neck solid"]}))
    mock(monkeypatch, handler)
    out = describe_service.parse(TEXT)
    assert out["parsed_by"] == "gemini" and out["activity"] == "moderate" and out["special_rules"] == ["Keep the neck solid"]
    assert "gemini-test" in seen["url"] and "test-key-123" not in seen["url"] and seen["key"] == "test-key-123"
    assert seen["body"]["generationConfig"]["responseMimeType"] == "application/json"
    assert "data, not instructions" in seen["body"]["systemInstruction"]["parts"][0]["text"]


def test_model_cannot_smuggle_stiffness_or_strength_targets(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    mock(monkeypatch, lambda r: httpx.Response(200, json=answer({
        "implant_type": "hip stem", "body_weight_kg": 9999, "activity": "extreme", "stiffness_gpa": {"z": 500}, "strength_mpa": 1e6,
        "special_rules": ["ok", "x" * 500]})))
    out = describe_service.parse(TEXT)
    assert set(out) == {"implant_type", "body_weight_kg", "activity", "special_rules", "notes", "parsed_by"}
    assert out["body_weight_kg"] == 82            # the absurd weight is dropped, then the offline value fills in
    assert out["activity"] == "moderate" and len(out["special_rules"][1]) <= 200


def _timeout(request):
    raise httpx.ConnectTimeout("slow")


@pytest.mark.parametrize("handler", [
    lambda r: httpx.Response(500, text="boom"),
    lambda r: httpx.Response(200, text="not json"),
    lambda r: httpx.Response(200, json={"candidates": []}),
    _timeout,
])
def test_any_gemini_failure_falls_back_offline_without_leaking_the_key(monkeypatch, handler):
    monkeypatch.setenv("GEMINI_API_KEY", "secret-key-xyz")
    mock(monkeypatch, handler)
    out = describe_service.parse(TEXT)
    assert out["parsed_by"] == "offline" and out["body_weight_kg"] == 82
    assert "offline rules were used" in " ".join(out["notes"]) and "secret-key-xyz" not in json.dumps(out)


def test_parse_endpoint_returns_only_the_four_fields(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    c = TestClient(app)
    up = c.post("/api/implants", files={"stl_file": ("s.stl", make_stem().export(file_type="stl"), "model/stl")},
                data={"material": "ti64", "description": ""})
    iid = up.json()["implant_id"]
    r = c.post(f"/api/implants/{iid}/parse", json={"description": "Knee component, 95 kg, very active. Avoid thin walls."})
    assert r.status_code == 200
    j = r.json()
    assert set(j["fields"]) == {"implant_type", "body_weight_kg", "activity", "special_rules"} and j["fields"]["body_weight_kg"] == 95
    assert j["parsed_by"] == "offline" and j["gemini_configured"] is False
    assert c.post(f"/api/implants/{iid}/parse", json={"description": "x" * 5000}).status_code == 422
