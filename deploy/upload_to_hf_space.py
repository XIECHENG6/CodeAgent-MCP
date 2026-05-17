"""
Upload CodeAgent-MCP to HuggingFace Spaces.

Run on Colab:
    !pip install huggingface_hub
    !python deploy/upload_to_hf_space.py --token YOUR_HF_TOKEN
"""

import argparse
import shutil
import tempfile
from pathlib import Path

from huggingface_hub import HfApi, create_repo


DEFAULT_SPACE_ID = "CodeAgent-MCP"
PROJECT_ROOT = Path(__file__).parent.parent

FILES_TO_UPLOAD = [
    "app.py",
    "src/__init__.py",
    "src/core/__init__.py",
    "src/core/config.py",
    "src/core/llm_client.py",
    "src/core/message.py",
    "src/core/agent_base.py",
    "src/core/orchestrator.py",
    "src/agents/__init__.py",
    "src/agents/planner.py",
    "src/agents/coder.py",
    "src/agents/reviewer.py",
    "src/utils/__init__.py",
    "src/utils/logger.py",
    "config/settings.yaml",
    "config/agents.yaml",
    "config/mcp_servers.yaml",
]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--token", required=True, help="HuggingFace token")
    parser.add_argument("--space-id", default=None)
    parser.add_argument("--private", action="store_true", default=False)
    args = parser.parse_args()

    api = HfApi(token=args.token)

    if args.space_id is None:
        username = api.whoami()["name"]
        args.space_id = f"{username}/{DEFAULT_SPACE_ID}"

    print(f"Creating/verifying Space: {args.space_id}")
    create_repo(
        repo_id=args.space_id,
        repo_type="space",
        space_sdk="gradio",
        private=args.private,
        exist_ok=True,
        token=args.token,
    )

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)

        readme_src = PROJECT_ROOT / "deploy" / "hf_space_readme.md"
        shutil.copy2(readme_src, tmp_path / "README.md")

        req_src = PROJECT_ROOT / "deploy" / "requirements_space.txt"
        shutil.copy2(req_src, tmp_path / "requirements.txt")

        for rel_path in FILES_TO_UPLOAD:
            src = PROJECT_ROOT / rel_path
            dst = tmp_path / rel_path
            dst.parent.mkdir(parents=True, exist_ok=True)
            if src.exists():
                shutil.copy2(src, dst)
            else:
                print(f"  WARNING: {rel_path} not found, skipping")

        print(f"Uploading {len(FILES_TO_UPLOAD) + 2} files to {args.space_id}...")
        api.upload_folder(
            folder_path=str(tmp_path),
            repo_id=args.space_id,
            repo_type="space",
        )

    print(f"\nDone! Space URL: https://huggingface.co/spaces/{args.space_id}")
    print("Note: First build may take 2-3 minutes.")


if __name__ == "__main__":
    main()
