#!/usr/bin/env bash
# Sync latex/ (flat layout) to overleaf-publish branch and push to Overleaf master.
# Overleaf expects main.tex, article.tex, figures/, tables/ at repo root — not latex/.
# Note: Overleaf prohibits git push --force; each publish must be a normal commit on top of remote master.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

PUBLISH_BRANCH="${OVERLEAF_PUBLISH_BRANCH:-overleaf-publish}"
OVERLEAF_REMOTE="${OVERLEAF_REMOTE:-overleaf}"
OVERLEAF_BRANCH="${OVERLEAF_BRANCH:-master}"
WORKTREE_DIR="${OVERLEAF_WORKTREE:-$REPO_ROOT/.overleaf-publish}"
LATEX_SRC="${OVERLEAF_LATEX_SRC:-$REPO_ROOT/latex}"
PAPERPILE_URL="${PAPERPILE_URL:-https://paperpile.com/eb/ltUsHRxzRF/paperpile.bib}"
PAPERPILE_BIB="${PAPERPILE_BIB:-$LATEX_SRC/paperpile.bib}"

if [[ ! -d "$LATEX_SRC" ]]; then
  echo "error: LaTeX source directory not found: $LATEX_SRC" >&2
  exit 1
fi

if ! git remote get-url "$OVERLEAF_REMOTE" &>/dev/null; then
  echo "error: git remote '$OVERLEAF_REMOTE' is not configured" >&2
  exit 1
fi

echo "==> Fetching $OVERLEAF_REMOTE/$OVERLEAF_BRANCH"
git fetch "$OVERLEAF_REMOTE" "$OVERLEAF_BRANCH"

# Create or reuse worktree, always starting from latest Overleaf master
if git worktree list --porcelain | grep -q "worktree $WORKTREE_DIR$"; then
  :
elif git show-ref --verify --quiet "refs/heads/$PUBLISH_BRANCH"; then
  git worktree add "$WORKTREE_DIR" "$PUBLISH_BRANCH"
else
  git worktree add -B "$PUBLISH_BRANCH" "$WORKTREE_DIR" "$OVERLEAF_REMOTE/$OVERLEAF_BRANCH"
fi

cd "$WORKTREE_DIR"
git checkout -B "$PUBLISH_BRANCH" "$OVERLEAF_REMOTE/$OVERLEAF_BRANCH"

echo "==> Syncing $LATEX_SRC -> flat tree on branch $PUBLISH_BRANCH"

# Remove all files in worktree except .git metadata
shopt -s dotglob nullglob
for item in * .[!.]* ..?*; do
  [[ -e "$item" ]] || continue
  base="$(basename "$item")"
  [[ "$base" == ".git" ]] && continue
  rm -rf "$item"
done
shopt -u dotglob nullglob

# Core TeX sources (flat at Overleaf root)
for f in main.tex article.tex preamble.tex metadata.tex; do
  if [[ ! -f "$LATEX_SRC/$f" ]]; then
    echo "error: missing $LATEX_SRC/$f" >&2
    exit 1
  fi
  cp "$LATEX_SRC/$f" .
done

# Bibliography: paperpile.bib is required by preamble (\addbibresource{paperpile.bib})
if [[ "${SKIP_UPDATE_REFS:-}" != "1" ]]; then
  echo "==> Fetching PaperPile bibliography from $PAPERPILE_URL"
  curl -fsSL -o "$PAPERPILE_BIB" "$PAPERPILE_URL"
fi
if [[ ! -f "$PAPERPILE_BIB" ]]; then
  echo "error: $PAPERPILE_BIB not found (run: make update-refs)" >&2
  exit 1
fi
cp "$PAPERPILE_BIB" .

# Figures and tables
mkdir -p figures tables
rsync -a --delete "$LATEX_SRC/figures/" figures/
rsync -a --delete "$LATEX_SRC/tables/" tables/

# Minimal ignore for LaTeX aux files if any leak in
cat > .gitignore <<'EOF'
*.aux
*.log
*.out
*.bbl
*.blg
*.bcf
*.run.xml
*.synctex.gz
*.fls
*.fdb_latexmk
main.pdf
EOF

git add -A

if git diff --cached --quiet; then
  echo "==> No changes to publish"
else
  COMMIT_MSG="${OVERLEAF_COMMIT_MSG:-Publish LaTeX tree to Overleaf (sync from latex/)}"
  git commit -m "$COMMIT_MSG"
  echo "==> Committed publish snapshot"
fi

echo "==> Pushing $PUBLISH_BRANCH -> $OVERLEAF_REMOTE/$OVERLEAF_BRANCH"
if ! git push "$OVERLEAF_REMOTE" "HEAD:$OVERLEAF_BRANCH"; then
  echo "error: push failed. Overleaf rejects force-push; pull/rebase in Overleaf UI if histories diverged." >&2
  exit 1
fi

echo "==> Done. Overleaf main document: main.tex (repo root)"
