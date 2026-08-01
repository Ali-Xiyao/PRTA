# Manifest boundary

- `exclusions/`: hashed patient exclusion registries only.
- `splits/`: patient-disjoint split manifests; generated files stay out of Git.
- `labels/`: label-manifest hashes and aggregate receipts, never raw reports.
- `receipts/`: local run receipts; generated JSON stays out of Git.

Do not commit patient identifiers, reports, image paths that reveal protected
storage, label payloads, feature caches, predictions, or credentials.
