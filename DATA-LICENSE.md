# Data And Artifact Licensing

This repository separates code, metadata, annotations, reports, and third-party
imagery.

## Code

The source code, scripts, tests, and configuration files are released under the
MIT License. See `LICENSE`.

## Manifests, Annotations, And Reports

The repository authors release the project-created manifests, annotations,
dataset cards, report tables, and paper-supporting metadata under CC BY 4.0,
unless a file states otherwise.

Attribution:

Sambetbayeva, A.; Shormakova, A.; Abaiuly, Y. Road Damage Detection and
Classification for Kazakhstan Road Imagery, 2026.

## Third-Party Images

Raw third-party images are not redistributed by default. Image source URLs,
authors/owners, license labels, and privacy-review status are recorded in
`data/manifests/images.csv` so users can reconstruct local image caches subject
to each source license.

Some source images may be available under Creative Commons, CC0, public-domain,
or platform-specific terms. Reusers are responsible for complying with the
license recorded for each source image, including attribution and share-alike
requirements where applicable.

## RDD2022

RDD2022 images and annotations are not redistributed in this repository. Users
must download RDD2022 from the official RoadDamageDetector/RDD2022 source and
follow its terms.

## Model Weights

Model weights are not included in the default public release. If weights are
released later, they should be attached as a separate release artifact with
their own license and training-data provenance statement.
