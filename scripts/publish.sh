#!/usr/bin/env bash
#
# Release ownmail to PyPI.
#
# Bumps the dev version to a release, runs lint & tests, builds, GPG-signs,
# tags, uploads to PyPI, then sets the next dev version — all in one shot.
#
# Usage:
#   ./scripts/publish.sh <major|minor|patch>              # publish to PyPI
#   ./scripts/publish.sh <major|minor|patch> --test       # publish to TestPyPI
#   ./scripts/publish.sh <major|minor|patch> --dry-run    # lint + test only, show plan
#
# Examples:
#   ./scripts/publish.sh patch              # 0.2.0-dev → release 0.2.0 → 0.2.1-dev
#   ./scripts/publish.sh minor --dry-run    # 0.2.0-dev → (shows plan, changes nothing)
#   ./scripts/publish.sh major --test       # 0.2.0-dev → release 0.2.0 → 1.0.0-dev (TestPyPI)
#
set -euo pipefail

cd "$(git rev-parse --show-toplevel)"

# Use venv Python if available
if [[ -x .venv/bin/python3 ]]; then
    PYTHON=".venv/bin/python3"
else
    PYTHON="python3"
fi

# ── Parse args ───────────────────────────────────────────────────────────────

PART=""
REPO="pypi"
DRY_RUN=false

for arg in "$@"; do
    case "$arg" in
        major|minor|patch) PART="$arg" ;;
        --test)    REPO="testpypi" ;;
        --dry-run) DRY_RUN=true ;;
        -h|--help)
            sed -n '3,18p' "$0" | sed 's/^# \?//'
            exit 0
            ;;
        *) echo "Unknown option: $arg"; exit 1 ;;
    esac
done

if [[ -z "$PART" ]]; then
    echo "Usage: $0 <major|minor|patch> [--test] [--dry-run]"
    exit 1
fi

# ── Helpers ──────────────────────────────────────────────────────────────────

PYPROJECT="pyproject.toml"

get_version() {
    $PYTHON -c "
import re, pathlib
text = pathlib.Path('$PYPROJECT').read_text()
m = re.search(r'^version\s*=\s*\"(.+?)\"', text, re.M)
print(m.group(1))
"
}

set_version() {
    sed -i '' "s/^version = \".*\"/version = \"$1\"/" "$PYPROJECT"
    sed -i '' "s/^__version__ = \".*\"/__version__ = \"$1\"/" "ownmail/__init__.py"
}

# ── Preflight ────────────────────────────────────────────────────────────────

CUR=$(get_version)
RELEASE="${CUR%-dev}"

echo "==> Current version: $CUR"

if [[ "$RELEASE" == "$CUR" ]]; then
    echo "❌ Current version '$CUR' is not a dev version (expected X.Y.Z-dev)."
    exit 1
fi

if ! git diff --quiet || ! git diff --cached --quiet; then
    echo "❌ Working tree is dirty. Commit or stash changes first."
    exit 1
fi

if ! command -v gpg &>/dev/null; then
    echo "❌ gpg not found. Install GPG to sign artifacts."
    exit 1
fi

if ! gpg --list-secret-keys --keyid-format=long 2>/dev/null | grep -q sec; then
    echo "❌ No GPG secret key found. Generate one with: gpg --full-generate-key"
    exit 1
fi

echo "==> Running lint..."
ruff check .

echo "==> Running tests..."
$PYTHON -m pytest --tb=short -q

# ── Compute versions ─────────────────────────────────────────────────────────

IFS='.' read -r major minor patch <<< "$RELEASE"
case "$PART" in
    major) NEXT="$((major + 1)).0.0-dev" ;;
    minor) NEXT="${major}.$((minor + 1)).0-dev" ;;
    patch) NEXT="${major}.${minor}.$((patch + 1))-dev" ;;
esac
TAG="v$RELEASE"

# ── Dry run: just show the plan ─────────────────────────────────────────────

if $DRY_RUN; then
    echo ""
    echo "==> Dry run — nothing will be changed. Plan:"
    echo "    1. Set version to $RELEASE, commit (release: v$RELEASE)"
    echo "    2. Build sdist + wheel"
    echo "    3. GPG-sign artifacts"
    echo "    4. Create signed tag $TAG"
    echo "    5. Set version to $NEXT, commit (chore: begin $NEXT development)"
    echo "    6. Upload to $REPO"
    echo "    7. git push origin master $TAG"
    exit 0
fi

# ── Bump to release version ─────────────────────────────────────────────────

echo "==> Setting release version: $RELEASE"
set_version "$RELEASE"
git add "$PYPROJECT" ownmail/__init__.py
git commit -S -m "release: v$RELEASE"

# ── Build ────────────────────────────────────────────────────────────────────

echo "==> Cleaning dist/..."
rm -rf dist/

echo "==> Building..."
$PYTHON -m build

# ── Sign ─────────────────────────────────────────────────────────────────────

echo "==> Signing artifacts with GPG..."
for f in dist/*.tar.gz dist/*.whl; do
    gpg --detach-sign --armor "$f"
    echo "    Signed: $f"
done

# ── Tag ──────────────────────────────────────────────────────────────────────

echo "==> Creating signed tag $TAG..."
git tag -s "$TAG" -m "Release $RELEASE"

# ── Bump to next dev version ────────────────────────────────────────────────

echo "==> Setting next dev version: $NEXT"
set_version "$NEXT"
git add "$PYPROJECT" ownmail/__init__.py
git commit -S -m "chore: begin $NEXT development"

# ── Upload ───────────────────────────────────────────────────────────────────

echo "==> Uploading to $REPO..."
twine upload --repository "$REPO" dist/*

echo ""
echo "✅ Published ownmail $RELEASE to $REPO"
echo ""
if [[ "$REPO" == "testpypi" ]]; then
    echo "   Install: pip install -i https://test.pypi.org/simple/ ownmail==$RELEASE"
else
    echo "   Install: pip install ownmail==$RELEASE"
fi
echo "   Tag:     $TAG"
echo "   Next:    $NEXT"
echo "   Push:    git push origin master $TAG"
