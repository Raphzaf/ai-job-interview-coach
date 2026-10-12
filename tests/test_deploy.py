"""Hugging Face Space deployment: assembled files, Space configuration, API calls (mocked)."""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("hf_deploy", ROOT / "deploy" / "huggingface" / "deploy.py")
hf_deploy = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(hf_deploy)


def _front_matter(text: str) -> dict[str, str]:
    block = text.split("---")[1]
    return dict(line.split(": ", 1) for line in block.strip().splitlines())


def test_assembled_space_contains_the_coach_only(tmp_path):
    out = hf_deploy.assemble(tmp_path / "space")
    assert (out / "Dockerfile").is_file() and (out / "requirements.txt").is_file() and (out / "constraints.txt").is_file()
    assert (out / "app" / "main.py").is_file()
    assert (out / "app" / "market_context" / "skill_demand_2023.json").is_file()
    assert (out / "data" / "examples" / "sample_cv.pdf").is_file()
    assert not (out / "market").exists() and not (out / "tests").exists()
    assert not list(out.rglob("__pycache__"))


def test_space_card_is_valid_for_the_hub():
    meta = _front_matter((ROOT / "deploy" / "huggingface" / "space_card.md").read_text(encoding="utf-8"))
    assert meta["sdk"] == "docker"
    assert len(meta["short_description"]) <= 60  # Hub limit
    exposed = re.search(r"^EXPOSE (\d+)", (ROOT / "Dockerfile").read_text(), re.MULTILINE).group(1)
    assert meta["app_port"] == exposed


def test_assemble_refuses_a_non_empty_folder(tmp_path):
    (tmp_path / "x").write_text("keep me")
    with pytest.raises(SystemExit):
        hf_deploy.assemble(tmp_path)


def test_space_url():
    assert hf_deploy.space_url("JDoe/ai_job.coach") == "https://jdoe-ai-job-coach.hf.space"


class FakeApi:
    def __init__(self):
        self.calls = []

    def __getattr__(self, name):
        def record(**kwargs):
            if name == "upload_folder":  # the folder is temporary: check it while it exists
                kwargs["files"] = sorted(p.name for p in Path(kwargs["folder_path"]).iterdir())
            self.calls.append((name, kwargs))
        return record


def test_deploy_with_llm_key_stores_a_secret(monkeypatch):
    monkeypatch.delenv("LLM_MODEL", raising=False)
    api = FakeApi()
    hf_deploy.deploy("jdoe/coach", token="t", llm_key="secret-key", api=api)
    names = [name for name, _ in api.calls]
    assert names == ["create_repo", "add_space_secret", "add_space_variable", "add_space_variable", "upload_folder"]
    assert api.calls[0][1]["space_sdk"] == "docker" and api.calls[0][1]["repo_type"] == "space"
    assert api.calls[1][1] == {"repo_id": "jdoe/coach", "key": "LLM_API_KEY", "value": "secret-key"}
    assert {"README.md", "Dockerfile", "app", "data"} <= set(api.calls[-1][1]["files"])


def test_deploy_without_llm_key_stores_nothing():
    api = FakeApi()
    hf_deploy.deploy("jdoe/coach", token="t", llm_key=None, api=api)
    assert [name for name, _ in api.calls] == ["create_repo", "upload_folder"]


def test_docker_build_is_pinned_to_the_verified_versions():
    def names(path):
        out = set()
        for line in (ROOT / path).read_text().splitlines():
            line = line.split("#")[0].strip()
            if line and not line.startswith("-"):
                out.add(re.split(r"[\[<>=!~ ]", line, maxsplit=1)[0].lower().replace("_", "-"))
        return out

    pinned = {line.split("==")[0].lower().replace("_", "-") for line in (ROOT / "constraints.txt").read_text().splitlines()
              if "==" in line and not line.startswith("#")}
    assert names("requirements.txt") <= pinned  # every direct dependency has an exact version
    dockerfile = (ROOT / "Dockerfile").read_text()
    assert "-c constraints.txt" in dockerfile and re.search(r"ARG TORCH_VERSION=\d", dockerfile)
