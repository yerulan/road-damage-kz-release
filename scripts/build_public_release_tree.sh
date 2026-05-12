#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="$ROOT/public_release"

rm -rf "$OUT"
mkdir -p "$OUT"

rsync -a \
  --exclude '*.egg-info' \
  --exclude '__pycache__' \
  --exclude 'collection-log.md' \
  --exclude 'main.log' \
  --exclude 'MDPI_template_ACS.zip' \
  --exclude 'mdpi_template_acs' \
  "$ROOT/src" \
  "$ROOT/configs" \
  "$ROOT/scripts" \
  "$ROOT/docs" \
  "$ROOT/tests" \
  "$ROOT/paper" \
  "$ROOT/reports/figures" \
  "$ROOT/pyproject.toml" \
  "$ROOT/README.md" \
  "$ROOT/LICENSE" \
  "$ROOT/DATA-LICENSE.md" \
  "$ROOT/CITATION.cff" \
  "$ROOT/.zenodo.json" \
  "$ROOT/RELEASE_NOTES.md" \
  "$OUT/"

mkdir -p "$OUT/data/manifests" "$OUT/reports"
cp "$ROOT/data/manifests/images.csv" "$OUT/data/manifests/"
cp "$ROOT/data/manifests/annotations.csv" "$OUT/data/manifests/"
cp "$ROOT/data/manifests/experiments.csv" "$OUT/data/manifests/"
cp "$ROOT/data/manifests/external_datasets.csv" "$OUT/data/manifests/"

for report in dataset_card.md experiment_table.csv paper_summary.json project_status.json; do
  if [[ -f "$ROOT/reports/$report" ]]; then
    cp "$ROOT/reports/$report" "$OUT/reports/"
  fi
done

cat > "$OUT/.gitignore" <<'EOF'
.venv/
__pycache__/
*.py[cod]
.DS_Store
.env.local
data/raw/
data/external/
data/processed/
runs/
*.pt
*.pth
*.onnx
*.engine
submission_package/
public_release/
EOF

echo "Clean public release tree written to $OUT"
echo "Review placeholders in CITATION.cff and .zenodo.json before publishing."
