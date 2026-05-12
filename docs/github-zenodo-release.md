# GitHub And Zenodo Release Procedure

Use this after the GPU experiments finish and the manuscript contains measured
YOLO11s/Ghost-CA-YOLO results.

## 1. Finalize Local Files

```bash
cd "/Users/belesprit/Documents/New project"

.venv/bin/python -m unittest discover -s tests
.venv/bin/roadkz figures --paper
.venv/bin/roadkz project-status --output reports/project_status.json

cd paper
tectonic --keep-logs main.tex
cd ..

scripts/build_submission_package.sh
```

## 2. Check For Forbidden Files

Do not publish:

- `data/raw/`
- `data/external/`
- `data/processed/`
- `runs/`
- `*.pt`, `*.pth`, `*.onnx`, `*.engine`
- unblurred third-party images
- RDD2022 archives or extracted images
- `.env.local`

Quick check:

```bash
git status --short
find . -maxdepth 3 \( -path "./data/raw" -o -path "./data/external" -o -path "./data/processed" -o -path "./runs" \) -prune -print
```

For a clean public repository without working-history clutter, generate a fresh
release tree:

```bash
scripts/build_public_release_tree.sh
```

Then review `public_release/` and publish that tree to a separate clean public
repository or orphan branch.

## 3. Confirm Repository URL

The configured repository URL is:

```text
https://github.com/yerulan/road-damage-kz
```

If the repository changes later, update `CITATION.cff`, `.zenodo.json`, and
`docs/submission-metadata.md`.

## 4. Create GitHub Repository

Recommended repository visibility before submission: private while results are
being finalized, then public before Zenodo archiving and journal submission.

```bash
git remote add origin git@github.com:yerulan/road-damage-kz.git
git branch -M main
git add .
git commit -m "Prepare Kazakhstan road damage paper release"
git push -u origin main
```

If a remote already exists, update the URL instead:

```bash
git remote set-url origin git@github.com:yerulan/road-damage-kz.git
```

## 5. Connect GitHub To Zenodo

1. Log into Zenodo.
2. Go to GitHub integration.
3. Enable the repository.
4. Create a GitHub release after final manuscript results are measured.
5. Zenodo will archive the release and mint a DOI.

Recommended final tag:

```bash
git tag -a v1.0.0 -m "Measured Ghost-CA-YOLO Kazakhstan road damage release"
git push origin v1.0.0
```

Then create a GitHub release from `v1.0.0`.

## 6. After Zenodo DOI Exists

Update:

- `CITATION.cff`
- `.zenodo.json`
- `paper/main.tex` Data Availability Statement
- `docs/submission-metadata.md`
- `README.md`

Then rebuild:

```bash
cd paper
tectonic --keep-logs main.tex
cd ..
scripts/build_submission_package.sh
```

Use the resulting package for Applied Sciences submission.
