#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

REPOS=(
  "fastapi https://github.com/fastapi/fastapi.git afe41126f624af30038cc8e17b2aaf60ebd4b838"
  "valibot https://github.com/open-circle/valibot.git 32247b362e7f80bc7c0b6c1cf180049ee4f8b884"
  "chi https://github.com/go-chi/chi.git 8b258c7bb28f97a5f2a856ff7ef962578fec9215"
  "pgrust https://github.com/malisper/pgrust.git c9aecbd05348e52a8ba21c688eec6258e8e8282f"
)

for entry in "${REPOS[@]}"; do
  read -r name url sha <<<"$entry"
  if [ ! -d "$name/.git" ]; then
    echo "cloning $name ..."
    git clone --quiet "$url" "$name"
  fi
  git -C "$name" fetch --quiet origin
  git -C "$name" -c advice.detachedHead=false checkout --quiet "$sha"
  echo "$name pinned at $sha"
done
