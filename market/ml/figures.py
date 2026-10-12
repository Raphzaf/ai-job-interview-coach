"""Figures for the ML results, drawn from data/processed/ml_results/*.json.

    python -m market.ml.figures
"""

from __future__ import annotations

import json

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.colors import LinearSegmentedColormap  # noqa: E402

from market import PROJECT_ROOT  # noqa: E402
from market.ml.train import RESULTS_DIR  # noqa: E402
from market.stats.run_stats import AXIS, BLUE, INK, INK_2, MUTED, ORANGE, SURFACE, style  # noqa: E402

FIG_DIR = PROJECT_ROOT / "reports" / "figures" / "ml"
SEQ_BLUE = ["#fcfcfb", "#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]
MODEL_LABELS = {"most_frequent": "Baseline: most frequent", "stratified": "Baseline: random (stratified)",
                "decision_tree": "Decision tree", "logistic_regression": "Logistic regression",
                "hist_gradient_boosting": "Gradient boosting (HGB)"}


def _save(fig, name: str, note: str) -> None:
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    fig.text(0.01, -0.03, note, fontsize=8.5, color=MUTED, ha="left", va="top")
    fig.savefig(FIG_DIR / f"{name}.png", dpi=200, bbox_inches="tight")
    plt.close(fig)


def model_comparison(role: dict) -> None:
    rows = [(MODEL_LABELS[k], v["macro_f1"], v["accuracy"]) for k, v in role["baselines"].items()]
    rows += [(MODEL_LABELS[k], v["test"]["macro_f1"], v["test"]["accuracy"]) for k, v in role["candidates"].items()]
    df = pd.DataFrame(rows, columns=["model", "macro_f1", "accuracy"]).sort_values("macro_f1")
    y = np.arange(len(df))
    fig, ax = plt.subplots(figsize=(9, 4.2))
    ax.barh(y + 0.19, df["macro_f1"], height=0.36, color=BLUE, label="Macro-F1 (main metric)")
    ax.barh(y - 0.19, df["accuracy"], height=0.36, color=ORANGE, label="Accuracy")
    for yi, (f1, acc) in enumerate(zip(df["macro_f1"], df["accuracy"])):
        ax.text(f1 + 0.01, yi + 0.19, f"{f1:.3f}", va="center", fontsize=9, color=INK_2)
        ax.text(acc + 0.01, yi - 0.19, f"{acc:.3f}", va="center", fontsize=9, color=INK_2)
    ax.set_yticks(y, df["model"])
    ax.set_xlim(0, 1)
    ax.grid(axis="y", visible=False)
    ax.set_xlabel("Score on the held-out test set (unseen companies)")
    ax.legend(loc="lower right")
    selected = MODEL_LABELS[role["selected_model"]]
    ax.set_title(f"Role-family classifier: models vs baselines (selected: {selected})")
    df.to_csv(RESULTS_DIR / "fig_model_comparison.csv", index=False)
    _save(fig, "ML_model_comparison", f"Test set: {role['test_rows']:,} postings from {role['test_companies']:,} companies "
          "never seen in training. Selection by cross-validated macro-F1.")


def confusion(role: dict) -> None:
    test = role["candidates"][role["selected_model"]]["test"]
    labels = test["labels"]
    cm = np.array(test["confusion_matrix"], dtype=float)
    pct = cm / cm.sum(axis=1, keepdims=True) * 100
    fig, ax = plt.subplots(figsize=(8.5, 7))
    im = ax.imshow(pct, cmap=LinearSegmentedColormap.from_list("seq", SEQ_BLUE), vmin=0, vmax=100)
    short = [lbl.replace("Machine Learning", "ML") for lbl in labels]
    ax.set_xticks(range(len(labels)), short, rotation=35, ha="right")
    ax.set_yticks(range(len(labels)), short)
    ax.grid(False)
    for i in range(len(labels)):
        for j in range(len(labels)):
            ax.text(j, i, f"{pct[i, j]:.0f}", ha="center", va="center", fontsize=9,
                    color=SURFACE if pct[i, j] > 55 else INK_2)
    ax.set_xlabel("Predicted role family")
    ax.set_ylabel("True role family")
    cb = fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    cb.outline.set_visible(False)
    cb.set_label("% of the true class (row)", color=INK_2)
    ax.set_title(f"Confusion matrix, {MODEL_LABELS[role['selected_model']]} (row-normalised %)")
    pd.DataFrame(pct.round(2), index=labels, columns=labels).to_csv(RESULTS_DIR / "fig_confusion_matrix_pct.csv")
    _save(fig, "ML_confusion_matrix", "Diagonal = recall per class. Test set, company-grouped split.")


def importance(role: dict, top: int = 15) -> None:
    df = pd.DataFrame(role["permutation_importance"]).head(top)[::-1]
    fig, ax = plt.subplots(figsize=(8.5, 0.38 * len(df) + 1.4))
    ax.barh(df["feature"].replace({"n_skills": "Number of skills"}), df["mean"], xerr=df["std"], color=BLUE,
            height=0.62, ecolor=INK_2, capsize=2)
    ax.grid(axis="y", visible=False)
    ax.set_xlabel("Drop in test macro-F1 when the feature is shuffled")
    ax.set_title("Which skills drive the role prediction (permutation importance)")
    df.to_csv(RESULTS_DIR / "fig_permutation_importance.csv", index=False)
    _save(fig, "ML_feature_importance", "Permutation importance of the selected model on 20,000 test postings, 5 repeats (mean ± sd).")


def seniority_roc(sen: dict) -> None:
    fig, ax = plt.subplots(figsize=(6.2, 5.6))
    ax.plot([0, 1], [0, 1], color=AXIS, lw=1, label="Random (AUC 0.50)")
    for (name, res), color in zip(sen["models"].items(), [BLUE, ORANGE]):
        pts = np.array(res["roc_points"])
        ax.plot(pts[:, 0], pts[:, 1], color=color, lw=2, label=f"{MODEL_LABELS[name]} (AUC {res['test_roc_auc']:.2f})")
    ax.set_xlabel("False positive rate")
    ax.set_ylabel("True positive rate (senior recall)")
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.legend(loc="lower right")
    ax.set_title("Secondary experiment: senior vs non-senior")
    _save(fig, "ML_seniority_roc", f"Test set: {sen['test_rows']:,} postings; senior share {sen['senior_share_test']:.1%}. "
          "Skills + role as features.")


def run_all() -> None:
    style()
    role = json.loads((RESULTS_DIR / "role_model.json").read_text())
    sen = json.loads((RESULTS_DIR / "seniority_experiment.json").read_text())
    model_comparison(role)
    confusion(role)
    importance(role)
    seniority_roc(sen)
    print("Figures:", sorted(p.name for p in FIG_DIR.glob("*.png")))


if __name__ == "__main__":
    run_all()
