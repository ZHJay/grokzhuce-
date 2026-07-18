#!/usr/bin/env bash
set -Eeuo pipefail

APP_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
BRANCH="${DEPLOY_BRANCH:-main}"
cd "$APP_DIR"

# 保留服务器上的 .env、keys/、private/ 和 reports/；同步只覆盖 Git 跟踪文件。
exec 9>"$APP_DIR/.deploy.lock"
flock -n 9 || { printf '%s\n' 'deploy already running'; exit 0; }

git fetch --prune origin "$BRANCH"
TARGET_REVISION="$(git rev-parse "origin/$BRANCH")"
if [[ -f .deployed-revision && "$(<.deployed-revision)" == "$TARGET_REVISION" ]]; then
  printf 'already deployed: %s\n' "$TARGET_REVISION"
  exit 0
fi

git reset --hard "$TARGET_REVISION"
test -f .env || { printf '%s\n' 'missing .env on server' >&2; exit 1; }

docker compose build solver
docker compose up -d solver
printf '%s\n' "$TARGET_REVISION" > .deployed-revision
docker compose ps
printf 'deployed revision: %s\n' "$TARGET_REVISION"
