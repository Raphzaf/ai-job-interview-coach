"""Deploy the coach to a Hugging Face Docker Space in one command.

    HF_TOKEN=hf_... LLM_API_KEY=... python deploy/huggingface/deploy.py <username>/<space-name>

What it does:
1. assembles the files the Space needs (Dockerfile, requirements, app/, sample
   documents, Space card) into a temporary folder;
2. creates the Space if it does not exist (public, Docker SDK);
3. stores LLM_API_KEY as a Space *secret* and the model settings as variables
   (skipped when LLM_API_KEY is not set: the Space then runs in offline mode);
4. uploads the files. Hugging Face builds the image and starts the app.

The upload uses the Hub API rather than `git push`, because the Hub rejects
binary files (the sample PDF/DOCX) pushed with plain git.

`--dry-run <dir>` only assembles the files into <dir>, without any network call.
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SPACE_CARD = Path(__file__).with_name("space_card.md")

# Files and folders copied into the Space (the coach only: no data pipeline, no PostgreSQL).
SPACE_FILES = ["Dockerfile", "requirements.txt", ".dockerignore"]
SPACE_DIRS = ["app", "data/examples"]

DEFAULT_LLM_VARIABLES = {
    "LLM_MODEL": "gemini-flash-latest",
    "LLM_BASE_URL": "https://generativelanguage.googleapis.com/v1beta/openai/",
}


def assemble(out_dir: Path) -> Path:
    """Copy the Space content into out_dir (which must be empty or absent)."""
    if out_dir.exists() and any(out_dir.iterdir()):
        raise SystemExit(f"{out_dir} is not empty; choose a new folder.")
    out_dir.mkdir(parents=True, exist_ok=True)
    for name in SPACE_FILES:
        shutil.copy2(ROOT / name, out_dir / name)
    for name in SPACE_DIRS:
        shutil.copytree(ROOT / name, out_dir / name, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    shutil.copy2(SPACE_CARD, out_dir / "README.md")
    return out_dir


def space_url(repo_id: str) -> str:
    """Public URL of the running app: https://<owner>-<name>.hf.space (lower-case, '_' and '.' become '-')."""
    return "https://" + repo_id.replace("/", "-").replace("_", "-").replace(".", "-").lower() + ".hf.space"


def deploy(repo_id: str, token: str, llm_key: str | None, api=None) -> None:
    if api is None:
        from huggingface_hub import HfApi

        api = HfApi(token=token)
    api.create_repo(repo_id=repo_id, repo_type="space", space_sdk="docker", private=False, exist_ok=True)
    print(f"Space ready: https://huggingface.co/spaces/{repo_id}")

    if llm_key:
        api.add_space_secret(repo_id=repo_id, key="LLM_API_KEY", value=llm_key)
        for key, default in DEFAULT_LLM_VARIABLES.items():
            api.add_space_variable(repo_id=repo_id, key=key, value=os.environ.get(key, default))
        print("LLM configured (API key stored as a Space secret).")
    else:
        print("LLM_API_KEY not set: the Space will run in labelled offline mode.")

    with tempfile.TemporaryDirectory() as tmp:
        folder = assemble(Path(tmp) / "space")
        api.upload_folder(repo_id=repo_id, repo_type="space", folder_path=str(folder),
                          commit_message="Deploy AI Job Market & Interview Coach")
    print("Files uploaded. Hugging Face is now building the image (about 5-10 minutes the first time).")
    print(f"App URL once built: {space_url(repo_id)}")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("repo_id", nargs="?", help="<username>/<space-name>, e.g. jdoe/ai-job-interview-coach")
    parser.add_argument("--dry-run", metavar="DIR", type=Path, help="only assemble the Space files into DIR")
    args = parser.parse_args(argv)

    if args.dry_run:
        folder = assemble(args.dry_run)
        print(f"Space files assembled in {folder}")
        return
    if not args.repo_id or "/" not in args.repo_id:
        parser.error("give the Space as <username>/<space-name>")
    token = os.environ.get("HF_TOKEN")
    if not token:
        sys.exit("Set HF_TOKEN to a Hugging Face access token with write permission "
                 "(https://huggingface.co/settings/tokens).")
    deploy(args.repo_id, token, os.environ.get("LLM_API_KEY"))


if __name__ == "__main__":
    main()
