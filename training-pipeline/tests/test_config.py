"""tests/test_config.py"""

from src.utils import load_config


def test_config_loads():
    cfg = load_config("configs/config.yaml")
    assert "huggingface" in cfg
    assert "t5_training" in cfg
    assert "evaluation" in cfg


def test_model_ids_present(tmp_path):
    cfg = load_config("configs/config.yaml")
    assert cfg["huggingface"]["t5_base_model"] == "google/flan-t5-xl"
    assert "gemma" in cfg["huggingface"]["gemma_base_model"].lower()
    assert "tinyllama" in cfg["huggingface"]["tinyllama_base_model"].lower()
