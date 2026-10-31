#!/usr/bin/env bash
set -euo pipefail

# Clone selected public repositories for local inspection only.
# This script does NOT install dependencies or merge their code into Trigger Point.
# Review each repository's current LICENSE and additional terms before reusing code.

DEST="${1:-references}"
mkdir -p "$DEST"

clone_or_update() {
  local name="$1"
  local url="$2"
  if [ -d "$DEST/$name/.git" ]; then
    echo "Updating $name"
    git -C "$DEST/$name" fetch --depth=1 origin
    git -C "$DEST/$name" checkout FETCH_HEAD
  else
    echo "Cloning $name"
    git clone --depth 1 "$url" "$DEST/$name"
  fi
  echo
  echo "=== $name ==="
  git -C "$DEST/$name" rev-parse HEAD
  if [ -f "$DEST/$name/LICENSE" ]; then
    sed -n '1,35p' "$DEST/$name/LICENSE"
  elif [ -f "$DEST/$name/LICENSE.md" ]; then
    sed -n '1,35p' "$DEST/$name/LICENSE.md"
  else
    echo "WARNING: no top-level LICENSE file found; inspect repository terms manually."
  fi
  echo
}

clone_or_update "crustdata-skills" "https://github.com/crustdata/skills.git"
clone_or_update "outbound-intelligence-engine" "https://github.com/Kazemkhani/outbound-intelligence-engine.git"
clone_or_update "yalc-gtm" "https://github.com/Othmane-Khadri/YALC-the-GTM-operating-system.git"
clone_or_update "anthropic-knowledge-work-plugins" "https://github.com/anthropics/knowledge-work-plugins.git"
clone_or_update "opengtm" "https://github.com/buildingopen/opengtm.git"

echo "Reference clones are in $DEST. Read docs/REPO_REUSE_POLICY.md before adapting code."
echo "TREG is intentionally not cloned by default because its current license includes additional hosted-service restrictions."
