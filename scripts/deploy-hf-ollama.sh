#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(git rev-parse --show-toplevel)"
SPACE_DIR="${OLLAMA_SPACE_DIR:-${ROOT_DIR}/ollama}"
HF_SPACE="${HF_OLLAMA_SPACE:-luhanxin/hf-ollama-service}"
HF_USERNAME="${HF_USERNAME:-luhanxin}"
HF_TOKEN="${HF_TOKEN:-}"

if [ -z "${HF_TOKEN}" ]; then
  echo "Missing HF_TOKEN. Create a Hugging Face token with write access and expose it as HF_TOKEN." >&2
  exit 1
fi

if ! git -C "${SPACE_DIR}" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  git -C "${ROOT_DIR}" submodule update --init --recursive -- ollama
fi

if [ ! -d "${SPACE_DIR}" ]; then
  echo "Ollama Space directory not found: ${SPACE_DIR}" >&2
  exit 1
fi

if [ -n "$(git -C "${SPACE_DIR}" status --porcelain)" ]; then
  echo "Ollama Space has uncommitted changes. Commit them inside ${SPACE_DIR} before deploying." >&2
  git -C "${SPACE_DIR}" status --short >&2
  exit 1
fi

cleanup() {
  git -C "${SPACE_DIR}" remote remove hf-deploy >/dev/null 2>&1 || true
}
trap cleanup EXIT

cleanup
git -C "${SPACE_DIR}" remote add hf-deploy "https://${HF_USERNAME}:${HF_TOKEN}@huggingface.co/spaces/${HF_SPACE}"
git -C "${SPACE_DIR}" push hf-deploy HEAD:main
