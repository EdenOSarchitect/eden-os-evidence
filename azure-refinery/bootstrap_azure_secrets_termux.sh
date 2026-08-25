#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

REPO="EdenOSarchitect/eden-os-evidence"

echo "EDEN Azure benchmark bootstrap"
echo "Repository: $REPO"
echo

if ! command -v gh >/dev/null 2>&1; then
  echo "Installing GitHub CLI..."
  pkg install -y gh
fi

if ! gh auth status >/dev/null 2>&1; then
  echo "GitHub authentication is required."
  gh auth login
fi

read -r -p "Azure OpenAI endpoint (https://<resource>.openai.azure.com): " AZURE_OPENAI_ENDPOINT
read -r -p "Azure OpenAI deployment name: " AZURE_OPENAI_DEPLOYMENT
read -r -s -p "Azure OpenAI API key (hidden): " AZURE_OPENAI_API_KEY
echo

if [[ -z "$AZURE_OPENAI_ENDPOINT" || -z "$AZURE_OPENAI_DEPLOYMENT" || -z "$AZURE_OPENAI_API_KEY" ]]; then
  echo "ERROR: all three Azure values are required." >&2
  exit 2
fi

printf '%s' "$AZURE_OPENAI_ENDPOINT" | gh secret set AZURE_OPENAI_ENDPOINT --repo "$REPO"
printf '%s' "$AZURE_OPENAI_DEPLOYMENT" | gh secret set AZURE_OPENAI_DEPLOYMENT --repo "$REPO"
printf '%s' "$AZURE_OPENAI_API_KEY" | gh secret set AZURE_OPENAI_API_KEY --repo "$REPO"
unset AZURE_OPENAI_API_KEY

echo
echo "Secrets stored in GitHub Actions. They were not written to disk or committed."
echo "Starting 1000-request EDEN Azure refinery benchmark..."
gh workflow run azure-refinery-benchmark.yml --repo "$REPO" -f requests=1000 -f concurrency=16

echo
echo "Run submitted. Latest runs:"
gh run list --repo "$REPO" --workflow azure-refinery-benchmark.yml --limit 3
