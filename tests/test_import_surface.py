"""Clean-clone import surface (no Streamlit run, no model pickle)."""


def test_data_loaders_import():
    from utils.data_loaders import load_model_info

    assert callable(load_model_info)


def test_control_plane_import():
    from src.control_plane.runtime import execute_guarded
    from src.governance.dpia_workspace.store import AssessmentStore

    assert callable(execute_guarded)
    assert AssessmentStore is not None


def test_api_server_imports_without_artifacts():
    import api_server

    assert api_server.app is not None
    assert api_server.model is None or api_server.model is not None


def test_api_health_without_forcing_artifacts():
    from fastapi.testclient import TestClient

    import api_server

    client = TestClient(api_server.app)
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert "model_loaded" in body
    assert body["status"] in {"healthy", "unhealthy"}
