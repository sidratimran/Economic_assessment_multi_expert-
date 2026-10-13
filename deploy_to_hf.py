"""Publish AsiaPulse AI to a Hugging Face Space (Docker) → one permanent link for the whole team.

Prerequisite (once):  hf auth login     (paste a *write* token from huggingface.co/settings/tokens)
Then:                 python deploy_to_hf.py [space-name]

Uploads the clean ../asiapulse_deploy folder (no .env, no caches). Re-run any time to update the site.
API keys are NOT uploaded — add them in the Space's Settings → Variables and secrets.
"""
import sys
from pathlib import Path

from huggingface_hub import HfApi

SRC = Path(__file__).resolve().parent.parent / "asiapulse_deploy"
name = sys.argv[1] if len(sys.argv) > 1 else "asiapulse-ai"

api = HfApi()
user = api.whoami()["name"]
repo_id = f"{user}/{name}"
assert not (SRC / ".env").exists(), "Refusing to upload: .env found in deploy folder"

api.create_repo(repo_id, repo_type="space", space_sdk="docker", exist_ok=True)
api.upload_folder(repo_id=repo_id, repo_type="space", folder_path=str(SRC),
                  ignore_patterns=[".env", "**/__pycache__/**", "data/live/**", "*.zip"],
                  commit_message="Deploy AsiaPulse AI")
print(f"\nDeployed. Build log & app:  https://huggingface.co/spaces/{repo_id}")
print(f"Direct link for your team:  https://{user.lower()}-{name.lower()}.hf.space")
