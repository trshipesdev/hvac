"""HVAC Efficiency Analyzer backend regression tests."""
import os
import io
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://unit-audit-2.preview.emergentagent.com").rstrip("/")
PASS = "changeme"
H = {"X-Api-Passphrase": PASS}


@pytest.fixture(scope="session")
def s():
    sess = requests.Session()
    sess.headers.update(H)
    return sess


# ---- Auth / health ----
def test_health():
    r = requests.get(f"{BASE_URL}/api/health", timeout=30)
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_auth_check_bad():
    r = requests.get(f"{BASE_URL}/api/auth/check", headers={"X-Api-Passphrase": "wrong"})
    assert r.status_code == 200
    assert r.json()["authenticated"] is False


def test_auth_check_ok():
    r = requests.get(f"{BASE_URL}/api/auth/check", headers=H)
    assert r.status_code == 200
    assert r.json()["authenticated"] is True


def test_unauthorized_protected():
    r = requests.get(f"{BASE_URL}/api/property")
    assert r.status_code == 401


# ---- Property ----
def test_property_get_and_put(s):
    r = s.get(f"{BASE_URL}/api/property")
    assert r.status_code == 200
    prop = r.json()
    assert "id" in prop
    upd = {"name": "TEST Property", "rate_usd_per_kwh": 0.14, "zip_code": "10001", "noaa_station_id": "GHCND:USW00094728"}
    r2 = s.put(f"{BASE_URL}/api/property", json=upd)
    assert r2.status_code == 200
    d = r2.json()
    assert d["name"] == "TEST Property"
    assert d["rate_usd_per_kwh"] == 0.14
    assert d["zip_code"] == "10001"
    # verify persistence
    r3 = s.get(f"{BASE_URL}/api/property")
    assert r3.json()["name"] == "TEST Property"


# ---- Units ----
def test_units_list_has_two(s):
    r = s.get(f"{BASE_URL}/api/units")
    assert r.status_code == 200
    units = r.json()
    assert len(units) >= 2, f"Expected >=2 units, got {len(units)}"


def test_units_crud(s):
    # create
    r = s.post(f"{BASE_URL}/api/units", json={"name": "TEST_Unit", "tonnage": 2.5})
    assert r.status_code == 200
    u = r.json()
    uid = u["id"]
    assert u["name"] == "TEST_Unit"
    # update
    r2 = s.put(f"{BASE_URL}/api/units/{uid}", json={"name": "TEST_Unit_Updated", "tonnage": 3.0})
    assert r2.status_code == 200
    assert r2.json()["name"] == "TEST_Unit_Updated"
    # delete
    r3 = s.delete(f"{BASE_URL}/api/units/{uid}")
    assert r3.status_code == 200
    # verify removed
    listing = s.get(f"{BASE_URL}/api/units").json()
    assert not any(x["id"] == uid for x in listing)


# ---- Green Button ingest ----
def test_sample_xml_download(s):
    r = s.get(f"{BASE_URL}/api/ingest/sample-xml")
    assert r.status_code == 200
    assert "xml" in r.headers.get("content-type", "").lower()
    assert len(r.content) > 500
    # cache for next test
    pytest.sample_xml_bytes = r.content


def test_green_button_ingest(s):
    xml = getattr(pytest, "sample_xml_bytes", None)
    if not xml:
        xml = s.get(f"{BASE_URL}/api/ingest/sample-xml").content
    files = {"file": ("sample.xml", io.BytesIO(xml), "application/xml")}
    r = s.post(f"{BASE_URL}/api/ingest/green-button", files=files)
    assert r.status_code == 200, r.text
    data = r.json()
    assert "inserted" in data and "skipped" in data
    assert (data["inserted"] + data["skipped"]) > 0
    assert "range_start" in data and "range_end" in data


# ---- Resideo ----
def test_resideo_status(s):
    r = s.get(f"{BASE_URL}/api/resideo/status")
    assert r.status_code == 200
    d = r.json()
    assert d.get("mock_mode") is True


def test_resideo_sync(s):
    r = s.post(f"{BASE_URL}/api/resideo/sync", params={"days": 10})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["units"] >= 2
    assert d["mock_mode"] is True


# ---- NOAA weather ----
def test_ingest_noaa(s):
    r = s.post(f"{BASE_URL}/api/ingest/noaa", params={"days": 30})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["source"] in ("noaa", "synthetic")


# ---- Attribution & Anomalies ----
def test_attribution_run(s):
    r = s.post(f"{BASE_URL}/api/attribution/run", params={"days": 30})
    assert r.status_code == 200
    d = r.json()
    assert "attributed" in d


def test_anomalies_run_and_list(s):
    r = s.post(f"{BASE_URL}/api/anomalies/run", params={"days": 30})
    assert r.status_code == 200
    d = r.json()
    assert d["anomalies"] >= 1, "Expected at least 1 anomaly from degraded unit"
    r2 = s.get(f"{BASE_URL}/api/anomalies")
    assert r2.status_code == 200
    lst = r2.json()
    assert len(lst) >= 1
    # filter by severity
    sev = lst[0]["severity"]
    r3 = s.get(f"{BASE_URL}/api/anomalies", params={"severity": sev})
    assert r3.status_code == 200
    assert all(a["severity"] == sev for a in r3.json())
    # filter by type
    t = lst[0]["type"]
    r4 = s.get(f"{BASE_URL}/api/anomalies", params={"type": t})
    assert all(a["type"] == t for a in r4.json())
    # filter by unit
    uid = lst[0]["unit_id"]
    r5 = s.get(f"{BASE_URL}/api/anomalies", params={"unit_id": uid})
    assert all(a["unit_id"] == uid for a in r5.json())


# ---- Dashboard ----
def test_dashboard_summary(s):
    r = s.get(f"{BASE_URL}/api/dashboard/summary", params={"days": 7})
    assert r.status_code == 200
    d = r.json()
    for k in ["total_kwh", "total_cost", "units", "active_anomalies", "critical_anomalies"]:
        assert k in d
    assert len(d["units"]) >= 2


def test_dashboard_timeline(s):
    r = s.get(f"{BASE_URL}/api/dashboard/timeline", params={"days": 7, "bucket": "hour"})
    assert r.status_code == 200
    d = r.json()
    assert "series" in d and "units" in d
    assert len(d["units"]) >= 2


def test_data_status(s):
    r = s.get(f"{BASE_URL}/api/dashboard/data-status")
    assert r.status_code == 200
    d = r.json()
    assert "energy_intervals" in d and "resideo" in d
    assert d["resideo"].get("mock_mode") is True


# ---- Pipeline ----
def test_pipeline_run(s):
    r = s.post(f"{BASE_URL}/api/pipeline/run", params={"days": 14}, timeout=120)
    assert r.status_code == 200, r.text
    d = r.json()
    for k in ["thermostats", "weather", "attribution", "anomalies"]:
        assert k in d


# ---- Bills ----
def test_bills_crud(s):
    from datetime import datetime, timedelta, timezone
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=7)
    payload = {"start": start.isoformat(), "end": end.isoformat(), "billed_kwh": 100.0, "billed_cost": 14.0}
    r = s.post(f"{BASE_URL}/api/bills", json=payload)
    assert r.status_code == 200, r.text
    b = r.json()
    assert "computed_kwh" in b and "computed_cost" in b
    bid = b["id"]
    r2 = s.get(f"{BASE_URL}/api/bills")
    assert any(x["id"] == bid for x in r2.json())
    r3 = s.delete(f"{BASE_URL}/api/bills/{bid}")
    assert r3.status_code == 200


# ---- Export ----
def test_export_csv(s):
    r = s.get(f"{BASE_URL}/api/export/csv", params={"days": 30})
    assert r.status_code == 200
    assert "csv" in r.headers.get("content-type", "").lower()
    text = r.content.decode()
    assert "kwh" in text.lower()


def test_export_pdf(s):
    r = s.get(f"{BASE_URL}/api/export/pdf", params={"days": 30})
    assert r.status_code == 200
    assert "pdf" in r.headers.get("content-type", "").lower()
    assert r.content[:4] == b"%PDF"
