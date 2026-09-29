from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_directions_lists_statuses_and_never_claims_fire_labels() -> None:
    response = client.get("/api/v1/ml/directions")
    assert response.status_code == 200
    items = response.json()
    statuses = {item["status"] for item in items}
    assert "PRODUCTION CANDIDATE" in statuses and "PROXY ONLY" in statuses
    proxies = [i for i in items if i["direction"] == "Incident Risk Proxy"]
    assert proxies and all(i["status"] == "PROXY ONLY" for i in proxies)


def test_models_expose_model_cards() -> None:
    response = client.get("/api/v1/ml/models")
    assert response.status_code == 200
    by_name = {item["name"]: item for item in response.json()}
    assert by_name["pump_baseline_72h"]["recipe"] == "logistic_regression"
    assert by_name["fan_72h"]["features"] > 0
    assert by_name["phase_24h"]["held_out"]["period"] == "2026H1"
    assert 0 < by_name["phase_24h"]["held_out"]["avg_precision"] <= 1


def test_results_listing_and_read_with_limit() -> None:
    listing = client.get("/api/v1/ml/results").json()
    assert "target_discovery_matrix.csv" in listing["tables"]
    url = "/api/v1/ml/results/tables/target_discovery_matrix.csv"
    response = client.get(url, params={"limit": 3})
    assert response.status_code == 200
    body = response.json()
    assert len(body["rows"]) == 3
    assert "sensor_type" in body["columns"]


def test_results_reject_unknown_group_and_path_traversal() -> None:
    assert client.get("/api/v1/ml/results/secrets/x.csv").status_code == 404
    assert client.get("/api/v1/ml/results/tables/..%2Fdirections.json").status_code == 404
    assert client.get("/api/v1/ml/results/tables/not_there.csv").status_code == 404
    too_many = client.get("/api/v1/ml/results/tables/x.csv", params={"limit": 100000})
    assert too_many.status_code == 422
