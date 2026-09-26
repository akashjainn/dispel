"""hearsay: forensic pipeline for synthetic-speech detection (HackGT 13, NSA HEARSAY).

Entry points:
  hearsay.orchestrator.Pipeline(model_dir).analyze(path_or_bytes, prior)  -> INTERFACES.md AnalyzeResponse
  hearsay.orchestrator.Pipeline(model_dir).tsv_score(path)                 -> float in (0, 1) for the NSA TSV
  python -m hearsay.cli predict <dir> -o <team>_predictions.tsv [--template NSA.tsv]
"""
__version__ = "0.3"
