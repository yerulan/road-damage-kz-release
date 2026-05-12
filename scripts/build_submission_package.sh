#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="$ROOT/submission_package"

rm -rf "$OUT"
mkdir -p "$OUT/source" "$OUT/supplementary"

cp "$ROOT/paper/main.pdf" "$OUT/manuscript.pdf"
cp "$ROOT/paper/cover-letter.md" "$OUT/cover-letter.md"

rsync -a \
  "$ROOT/paper/main.tex" \
  "$ROOT/paper/Definitions" \
  "$ROOT/reports/figures" \
  "$OUT/source/"

rsync -a \
  --exclude '*.egg-info' \
  --exclude '__pycache__' \
  --exclude 'collection-log.md' \
  "$ROOT/src" \
  "$ROOT/configs" \
  "$ROOT/scripts" \
  "$ROOT/docs" \
  "$ROOT/tests" \
  "$ROOT/pyproject.toml" \
  "$ROOT/README.md" \
  "$ROOT/LICENSE" \
  "$ROOT/DATA-LICENSE.md" \
  "$ROOT/CITATION.cff" \
  "$ROOT/.zenodo.json" \
  "$ROOT/RELEASE_NOTES.md" \
  "$OUT/supplementary/"

mkdir -p "$OUT/supplementary/data/manifests" "$OUT/supplementary/reports"
cp "$ROOT/data/manifests/images.csv" "$OUT/supplementary/data/manifests/"
cp "$ROOT/data/manifests/annotations.csv" "$OUT/supplementary/data/manifests/"
cp "$ROOT/data/manifests/experiments.csv" "$OUT/supplementary/data/manifests/"
cp "$ROOT/data/manifests/external_datasets.csv" "$OUT/supplementary/data/manifests/"

for report in dataset_card.md experiment_table.csv paper_summary.json project_status.json; do
  if [[ -f "$ROOT/reports/$report" ]]; then
    cp "$ROOT/reports/$report" "$OUT/supplementary/reports/"
  fi
done

(
  cd "$OUT"
  zip -qr manuscript-source.zip source
  zip -qr supplementary.zip supplementary
)

echo "Submission package written to $OUT"
echo "Do not add raw third-party images, RDD archives, extracted RDD images, or runs/ to this package."
