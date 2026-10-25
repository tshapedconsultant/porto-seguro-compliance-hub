"""Clean-clone import surface (no Streamlit run, no model pickle)."""


def test_data_loaders_import():
    from utils.data_loaders import load_model_info

    assert callable(load_model_info)


def test_control_plane_import():
    from src.control_plane.runtime import execute_guarded
    from src.governance.dpia_workspace.store import AssessmentStore

    assert callable(execute_guarded)
    assert AssessmentStore is not None
