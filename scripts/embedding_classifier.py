"""
Embedding-based adversarial query classifier.

Embeds adversarial queries with a sentence-transformer
model, trains a logistic regression classifier, and
reports detection rates via 5-fold cross-validation.

Usage:
    python scripts/embedding_classifier.py
    python scripts/embedding_classifier.py --cache-only
    python scripts/embedding_classifier.py --skip-embed
    python scripts/embedding_classifier.py --model BAAI/bge-large-en-v1.5

Environment:
    EMBED_CACHE_DIR: directory for cached .npy files
        (default: evals/embeddings)
    HF_HOME: HuggingFace model cache directory
        (default: ~/.cache/huggingface)
"""

import argparse
import json
import os
import re
import sys

from pathlib import Path

import numpy as np

from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    classification_report,
    precision_recall_fscore_support,
)
from sklearn.model_selection import (
    StratifiedKFold,
    cross_val_predict,
)

from text_to_sql.app_logger import get_logger


logger = get_logger(__name__)

QUERIES_PATH = Path("evals/adversarial_queries.json")
EMBED_DIR = Path(os.environ.get("EMBED_CACHE_DIR", "evals/embeddings"))
DEFAULT_MODEL = "BAAI/bge-m3"

ADVERSARIAL_LABELS = {"blocked", "blocked_extended_pii"}
BENIGN_LABELS = {"allowed"}
EXCLUDED_LABELS = {"uncertain"}
EXCLUDED_VECTORS = {"schema_metadata"}


def _cache_stem(model_name: str) -> str:
    """
    Helper function used to derive a filesystem-safe
    stem from a model name, e.g. "BAAI/bge-m3" becomes
    "bge_m3".
    """
    base = model_name.split("/")[-1]
    return re.sub(r"[^a-zA-Z0-9]", "_", base)


def build_labels(queries: list[dict]) -> np.ndarray:
    """
    Convert expected_outcome to binary labels.

    Returns:
        numpy array: 1 = adversarial, 0 = benign.
    """
    labels = []
    for q in queries:
        outcome = q["expected_outcome"]
        if outcome in ADVERSARIAL_LABELS:
            labels.append(1)
        elif outcome in BENIGN_LABELS:
            labels.append(0)
        else:
            raise ValueError(f"Unexpected: {outcome}")
    y = np.array(labels)
    logger.info("Labels: %d adversarial, %d benign",
                int(y.sum()), len(y) - int(y.sum()))
    return y


def compute_embeddings(
    queries: list[dict], model_name: str,
) -> np.ndarray:
    """
    Compute embeddings and cache to disk.

    Args:
        queries: list of query dicts with nl_query
        model_name: HuggingFace model identifier

    Returns:
        numpy array of shape (n_queries, dim).
    """
    from sentence_transformers import (
        SentenceTransformer,
    )

    logger.info("Loading %s...", model_name)
    model = SentenceTransformer(model_name)
    texts = [q["nl_query"] for q in queries]
    logger.info("Embedding %d queries...", len(texts))
    embeddings = np.array(model.encode(
        sentences=texts,
        show_progress_bar=True,
        normalize_embeddings=True,
        batch_size=32,
    ))

    EMBED_DIR.mkdir(parents=True, exist_ok=True)
    stem = _cache_stem(model_name=model_name)
    npy_path = EMBED_DIR / f"{stem}.npy"
    ids_path = EMBED_DIR / f"{stem}_ids.json"
    np.save(npy_path, embeddings)
    with open(ids_path, "w", encoding="utf-8") as f:
        json.dump([q["id"] for q in queries], f)

    logger.info("Cached %s to %s",
                embeddings.shape, npy_path)
    return embeddings


def load_cached_embeddings(
    model_name: str,
) -> np.ndarray:
    """
    Load cached embeddings from disk.

    Args:
        model_name: HuggingFace model identifier

    Returns:
        numpy array of shape (n_queries, dim).
    """
    stem = _cache_stem(model_name=model_name)
    npy_path = EMBED_DIR / f"{stem}.npy"
    if not npy_path.exists():
        raise FileNotFoundError(
            f"{npy_path} not found. "
            f"Run without --skip-embed first.")
    embeddings = np.load(npy_path)
    logger.info("Loaded cached embeddings: %s",
                embeddings.shape)
    return embeddings


def load_queries() -> list[dict]:
    """
    Load adversarial queries from JSON, filtering
    to pipeline-executable queries only.

    Returns:
        List of query dicts with nl_query and
        expected_outcome fields.
    """
    with open(QUERIES_PATH, encoding="utf-8") as f:
        all_qs = json.load(f)
    filtered = [
        q for q in all_qs
        if q["vector"] not in EXCLUDED_VECTORS
        and q["expected_outcome"] not in EXCLUDED_LABELS
    ]
    logger.info("Loaded %d queries, %d after filtering",
                len(all_qs), len(filtered))
    return filtered


def main() -> None:
    """
    Entry point. Parse args and run embedding
    classifier experiment.
    """
    parser = argparse.ArgumentParser(
        description="Embedding-based adversarial "
        "query classifier",
    )
    parser.add_argument(
        "--model", default=DEFAULT_MODEL,
        help=f"Sentence-transformer model "
        f"(default: {DEFAULT_MODEL})",
    )
    parser.add_argument(
        "--dim", type=int, default=None,
        help="Truncate embeddings to this dimension "
        "(Matryoshka). Re-normalizes after truncation.",
    )
    embed_group = parser.add_mutually_exclusive_group()
    embed_group.add_argument(
        "--cache-only", action="store_true",
        help="Compute and cache embeddings, then exit",
    )
    embed_group.add_argument(
        "--skip-embed", action="store_true",
        help="Load cached embeddings instead of "
        "recomputing",
    )
    args = parser.parse_args()

    queries = load_queries()
    y = build_labels(queries=queries)

    if args.skip_embed:
        X = load_cached_embeddings(
            model_name=args.model,
        )
        if X.shape[0] != len(queries):
            logger.error(
                "Cache has %d rows but %d queries. "
                "Re-run without --skip-embed.",
                X.shape[0], len(queries))
            sys.exit(1)
    else:
        X = compute_embeddings(
            queries=queries, model_name=args.model,
        )

    if args.cache_only:
        logger.info("Embeddings cached. Exiting.")
        return

    if args.dim:
        if args.dim > X.shape[1]:
            logger.error("--dim %d exceeds native %d",
                         args.dim, X.shape[1])
            sys.exit(1)
        X = X[:, :args.dim]
        norms = np.linalg.norm(X, axis=1, keepdims=True)
        X = X / norms
        logger.info("Truncated to %d dims, re-normalized",
                    args.dim)

    run_classification(X=X, y=y)


def run_classification(
    X: np.ndarray, y: np.ndarray,
) -> None:
    """
    5-fold stratified cross-validation with logistic
    regression. Prints classification report and
    per-fold recall.
    """
    clf = LogisticRegression(
        max_iter=1000, class_weight="balanced",
        random_state=42,
    )
    cv = StratifiedKFold(
        n_splits=5, shuffle=True, random_state=42,
    )
    y_proba = cross_val_predict(
        estimator=clf, X=X, y=y, cv=cv,
        method="predict_proba",
    )[:, 1]
    y_pred = (y_proba >= 0.5).astype(int)

    print("\n=== 5-Fold CV Classification Report ===")
    print(classification_report(
        y_true=y, y_pred=y_pred,
        target_names=["benign", "adversarial"],
    ))

    p, r, f1, _ = precision_recall_fscore_support(
        y_true=y, y_pred=y_pred,
        average="binary", pos_label=1,
    )
    print(f"Adversarial detection: precision={p:.1%},"
          f" recall={r:.1%}, F1={f1:.1%}")

    print("\n=== Per-Fold Recall (adversarial) ===")
    for i, (_, test_idx) in enumerate(
        cv.split(X, y), start=1,
    ):
        _, recall, _, _ = precision_recall_fscore_support(
            y_true=y[test_idx], y_pred=y_pred[test_idx],
            average="binary", pos_label=1,
        )
        n_adv = int(y[test_idx].sum())
        print(f"  Fold {i}: recall={recall:.1%} "
              f"({n_adv} adversarial in fold)")

    # Threshold sweep using CV probability estimates
    print("\n=== Threshold Sweep ===")
    print(f"{'Threshold':>10} {'Precision':>10} "
          f"{'Recall':>10} {'F1':>10} {'FPR':>10}")
    for t in (0.3, 0.5, 0.7, 0.9):
        y_t = (y_proba >= t).astype(int)
        p_t, r_t, f1_t, _ = precision_recall_fscore_support(
            y_true=y, y_pred=y_t,
            average="binary", pos_label=1,
        )
        fp = ((y_t == 1) & (y == 0)).sum()
        fpr = fp / (y == 0).sum()
        print(f"{t:>10.1f} {p_t:>10.1%} "
              f"{r_t:>10.1%} {f1_t:>10.1%} "
              f"{fpr:>10.1%}")


if __name__ == "__main__":
    main()
