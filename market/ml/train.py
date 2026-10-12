"""Train, tune and evaluate the ML models (scikit-learn).

    python -m market.ml.train          # needs DATABASE_URL (read-only role)

Main task:  predict the ROLE FAMILY of a data-job posting from its skill profile
            (7 classes). Used later by the interview coach to position a CV.
Secondary:  predict SENIOR vs non-senior from skills (+ role), reported as an
            honest experiment (Phase 4 showed skill differences are small).

Methodology
- Company-grouped train/test split (80/20): no company appears in both sets,
  so templated postings of one employer cannot inflate test scores.
- Baselines: DummyClassifier (most frequent, stratified).
- Candidates: Logistic Regression, Decision Tree, Histogram Gradient Boosting.
- Hyper-parameters tuned with StratifiedGroupKFold (3 folds) on a stratified
  subsample of the TRAINING set, optimising macro-F1 (classes are imbalanced).
- Model selection uses cross-validation only; the test set is used once, at
  the end, to report every candidate.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.base import clone
from sklearn.dummy import DummyClassifier
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.inspection import permutation_importance
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score, average_precision_score, balanced_accuracy_score, classification_report, confusion_matrix,
    f1_score, roc_auc_score,
)
from sklearn.model_selection import GridSearchCV, GroupShuffleSplit, StratifiedGroupKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.tree import DecisionTreeClassifier

from market import PROCESSED_DIR, PROJECT_ROOT
from market.ml.data import Dataset, build_features, load_dataset

RESULTS_DIR = PROCESSED_DIR / "ml_results"
MODEL_DIR = PROJECT_ROOT / "models"
SEED = 42

CANDIDATES = {
    "logistic_regression": (
        make_pipeline(StandardScaler(), LogisticRegression(max_iter=2000)),
        {"logisticregression__C": [0.01, 0.1, 1.0], "logisticregression__class_weight": [None, "balanced"]},
    ),
    "decision_tree": (
        DecisionTreeClassifier(random_state=SEED),
        {"max_depth": [8, 14, 20], "min_samples_leaf": [20, 100], "class_weight": [None, "balanced"]},
    ),
    "hist_gradient_boosting": (
        HistGradientBoostingClassifier(random_state=SEED, early_stopping=False, max_iter=200),
        {"learning_rate": [0.1, 0.2], "max_leaf_nodes": [31, 63], "class_weight": [None, "balanced"]},
    ),
}


def grouped_split(ds: Dataset, test_size: float = 0.2):
    splitter = GroupShuffleSplit(n_splits=1, test_size=test_size, random_state=SEED)
    train_idx, test_idx = next(splitter.split(ds.X, ds.y_role, ds.groups))
    assert not set(ds.groups.iloc[train_idx]) & set(ds.groups.iloc[test_idx]), "company leakage"
    return train_idx, test_idx


def stratified_subsample(y: pd.Series, n: int) -> np.ndarray:
    """Positions of a class-stratified random subsample (for affordable CV tuning)."""
    rng = np.random.default_rng(SEED)
    frac = min(1.0, n / len(y))
    picks = [rng.choice(np.flatnonzero(y.to_numpy() == c), size=max(1, int(round((y == c).sum() * frac))), replace=False)
             for c in sorted(y.unique())]
    return np.sort(np.concatenate(picks))


def multiclass_metrics(y_true, y_pred, labels) -> dict:
    return {
        "accuracy": round(accuracy_score(y_true, y_pred), 4),
        "balanced_accuracy": round(balanced_accuracy_score(y_true, y_pred), 4),
        "macro_f1": round(f1_score(y_true, y_pred, average="macro"), 4),
        "weighted_f1": round(f1_score(y_true, y_pred, average="weighted"), 4),
        "per_class": {k: {m: round(v, 4) for m, v in d.items()} for k, d in classification_report(
            y_true, y_pred, labels=labels, output_dict=True, zero_division=0).items() if k in labels},
        "confusion_matrix": confusion_matrix(y_true, y_pred, labels=labels).tolist(),
        "labels": list(labels),
    }


def tune(name: str, X, y, groups) -> GridSearchCV:
    estimator, grid = CANDIDATES[name]
    search = GridSearchCV(estimator, grid, scoring="f1_macro", cv=StratifiedGroupKFold(n_splits=3, shuffle=True, random_state=SEED),
                          n_jobs=-1, refit=False)
    search.fit(X, y, groups=groups)
    return search


def run_role_model(ds: Dataset, tune_rows: int = 120_000) -> dict:
    labels = sorted(ds.y_role.unique())
    train_idx, test_idx = grouped_split(ds)
    X_train, X_test = ds.X.iloc[train_idx], ds.X.iloc[test_idx]
    y_train, y_test = ds.y_role.iloc[train_idx], ds.y_role.iloc[test_idx]
    sub = stratified_subsample(y_train, tune_rows)

    results = {"task": "role_family (7 classes) from coach-taxonomy skills",
               "rows": int(len(ds.X)), "features": int(ds.X.shape[1]), "train_rows": int(len(train_idx)),
               "test_rows": int(len(test_idx)), "train_companies": int(ds.groups.iloc[train_idx].nunique()),
               "test_companies": int(ds.groups.iloc[test_idx].nunique()), "tuning_rows": int(len(sub)),
               "class_distribution_train": y_train.value_counts().to_dict(),
               "class_distribution_test": y_test.value_counts().to_dict(), "baselines": {}, "candidates": {}}

    for strategy in ("most_frequent", "stratified"):
        dummy = DummyClassifier(strategy=strategy, random_state=SEED).fit(X_train, y_train)
        results["baselines"][strategy] = multiclass_metrics(y_test, dummy.predict(X_test), labels)

    fitted = {}
    for name in CANDIDATES:
        started = time.time()
        search = tune(name, X_train.iloc[sub], y_train.iloc[sub], ds.groups.iloc[train_idx].iloc[sub])
        model = clone(CANDIDATES[name][0]).set_params(**search.best_params_).fit(X_train, y_train)
        pred = model.predict(X_test)
        cv = pd.DataFrame(search.cv_results_)
        best = cv.loc[cv["rank_test_score"] == 1].iloc[0]
        results["candidates"][name] = {
            "best_params": {k: v for k, v in search.best_params_.items()},
            "cv_macro_f1_mean": round(float(best["mean_test_score"]), 4),
            "cv_macro_f1_std": round(float(best["std_test_score"]), 4),
            "cv_grid": [{"params": p, "macro_f1": round(float(s), 4)}
                        for p, s in zip(cv["params"], cv["mean_test_score"])],
            "test": multiclass_metrics(y_test, pred, labels),
            "seconds": round(time.time() - started, 1),
        }
        fitted[name] = model
        print(f"{name}: CV macro-F1 {best['mean_test_score']:.4f} | test macro-F1 "
              f"{results['candidates'][name]['test']['macro_f1']} ({time.time() - started:.0f}s)")

    best_name = max(results["candidates"], key=lambda n: results["candidates"][n]["cv_macro_f1_mean"])
    final = fitted[best_name]
    results["selected_model"] = best_name
    results["selection_rule"] = "highest cross-validated macro-F1 on the training data (test set not used for selection)"

    # Interpretation 1: permutation importance of the selected model (test subsample).
    rng = np.random.default_rng(SEED)
    pi_idx = rng.choice(len(X_test), size=min(20_000, len(X_test)), replace=False)
    pi = permutation_importance(final, X_test.iloc[pi_idx], y_test.iloc[pi_idx], scoring="f1_macro",
                                n_repeats=5, random_state=SEED, n_jobs=-1)
    results["permutation_importance"] = sorted(
        [{"feature": f, "mean": round(float(m), 5), "std": round(float(s), 5)}
         for f, m, s in zip(X_test.columns, pi.importances_mean, pi.importances_std)],
        key=lambda d: d["mean"], reverse=True)

    # Interpretation 2: logistic-regression coefficients per class (standardised features).
    lr = fitted["logistic_regression"]
    coef = lr.named_steps["logisticregression"].coef_
    results["logistic_top_features"] = {
        cls: {"positive": [(ds.X.columns[j], round(float(coef[i, j]), 3)) for j in np.argsort(coef[i])[::-1][:6]],
              "negative": [(ds.X.columns[j], round(float(coef[i, j]), 3)) for j in np.argsort(coef[i])[:4]]}
        for i, cls in enumerate(lr.classes_)}

    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    joblib.dump({"model": final, "feature_skills": ds.feature_skills, "classes": list(final.classes_),
                 "trained_on": "lukebarousse/data_jobs 2023 (company-grouped 80% train split)",
                 "metrics_test": results["candidates"][best_name]["test"], "model_name": best_name},
                MODEL_DIR / "role_classifier.joblib", compress=3)
    results["model_file"] = "models/role_classifier.joblib"
    return results, final, (X_test, y_test)


def run_seniority_experiment(ds: Dataset, tune_rows: int = 120_000) -> dict:
    """Binary senior vs non-senior within the roles that have a Senior variant."""
    roles = ["Data Analyst", "Data Engineer", "Data Scientist"]
    mask = ds.y_role.isin(roles).to_numpy()
    X = pd.concat([ds.X[mask], pd.get_dummies(ds.y_role[mask], prefix="role", dtype=np.float32)], axis=1)
    y, groups = ds.y_senior[mask], ds.groups[mask]
    sub_ds = Dataset(X=X, y_role=y.astype(str), y_senior=y, groups=groups, feature_skills=ds.feature_skills)
    train_idx, test_idx = grouped_split(sub_ds)
    X_train, X_test, y_train, y_test = X.iloc[train_idx], X.iloc[test_idx], y.iloc[train_idx], y.iloc[test_idx]
    sub = stratified_subsample(y_train.astype(str), tune_rows)
    out = {"task": "senior vs non-senior (Data Analyst/Engineer/Scientist) from skills + role",
           "rows": int(len(X)), "train_rows": int(len(train_idx)), "test_rows": int(len(test_idx)),
           "senior_share_test": round(float(y_test.mean()), 4), "models": {}}
    prevalence = float(y_test.mean())
    out["baseline"] = {"roc_auc": 0.5, "average_precision": round(prevalence, 4),
                       "note": "random ranking: ROC AUC 0.5, average precision = senior share"}
    for name, (est, grid) in {
        "logistic_regression": (make_pipeline(StandardScaler(), LogisticRegression(max_iter=2000, class_weight="balanced")),
                                {"logisticregression__C": [0.01, 0.1, 1.0]}),
        "hist_gradient_boosting": (HistGradientBoostingClassifier(random_state=SEED, early_stopping=False, max_iter=200,
                                                                  class_weight="balanced"),
                                   {"learning_rate": [0.1, 0.2], "max_leaf_nodes": [31, 63]}),
    }.items():
        search = GridSearchCV(est, grid, scoring="roc_auc", cv=StratifiedGroupKFold(n_splits=3, shuffle=True, random_state=SEED),
                              n_jobs=-1, refit=False).fit(X_train.iloc[sub], y_train.iloc[sub], groups=groups.iloc[train_idx].iloc[sub])
        model = clone(est).set_params(**search.best_params_).fit(X_train, y_train)
        proba = model.predict_proba(X_test)[:, 1]
        pred = proba >= 0.5
        out["models"][name] = {
            "best_params": search.best_params_, "cv_roc_auc": round(float(search.best_score_), 4),
            "test_roc_auc": round(roc_auc_score(y_test, proba), 4),
            "test_average_precision": round(average_precision_score(y_test, proba), 4),
            "test_balanced_accuracy": round(balanced_accuracy_score(y_test, pred), 4),
            "test_f1_senior": round(f1_score(y_test, pred), 4),
            "confusion_matrix": confusion_matrix(y_test, pred, labels=[False, True]).tolist(),
            "roc_points": _roc_points(y_test.to_numpy(), proba),
        }
        print(f"seniority {name}: test ROC AUC {out['models'][name]['test_roc_auc']}")
    return out


def _roc_points(y, proba, n: int = 50) -> list[list[float]]:
    from sklearn.metrics import roc_curve

    fpr, tpr, _ = roc_curve(y, proba)
    idx = np.linspace(0, len(fpr) - 1, n).astype(int)
    return [[round(float(fpr[i]), 4), round(float(tpr[i]), 4)] for i in idx]


def predict_roles(model_bundle: dict, skills: list[str], top: int = 3) -> list[dict]:
    """Role-family probabilities for one skill list (e.g. skills extracted from a CV)."""
    X = build_features(pd.Series([skills]), model_bundle["feature_skills"])
    proba = model_bundle["model"].predict_proba(X)[0]
    order = np.argsort(proba)[::-1][:top]
    return [{"role_family": model_bundle["classes"][i], "probability": round(float(proba[i]), 4)} for i in order]


def topk_accuracy(model, X, y, ks=(1, 2, 3)) -> dict:
    """Share of postings whose true role is among the model's k most probable roles."""
    proba = model.predict_proba(X)
    order = np.argsort(proba, axis=1)[:, ::-1]
    classes = np.asarray(model.classes_)
    truth = y.to_numpy()
    return {f"top_{k}": round(float(np.mean([t in classes[o[:k]] for t, o in zip(truth, order)])), 4) for k in ks}


def evaluate_saved_model(ds: Dataset | None = None) -> dict:
    """Top-k accuracy of the saved model on the same (deterministic) company-grouped test split."""
    ds = ds or load_dataset()
    _, test_idx = grouped_split(ds)
    bundle = joblib.load(MODEL_DIR / "role_classifier.joblib")
    return topk_accuracy(bundle["model"], ds.X.iloc[test_idx], ds.y_role.iloc[test_idx])


def run_all() -> dict:
    started = time.time()
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    ds = load_dataset()
    print(f"Dataset: {ds.X.shape[0]:,} postings x {ds.X.shape[1]} features ({time.time() - started:.0f}s)")
    role, final, (X_test, y_test) = run_role_model(ds)
    role["selected_model_topk_accuracy"] = topk_accuracy(final, X_test, y_test)
    (RESULTS_DIR / "role_model.json").write_text(json.dumps(role, indent=2, default=str), encoding="utf-8")
    seniority = run_seniority_experiment(ds)
    (RESULTS_DIR / "seniority_experiment.json").write_text(json.dumps(seniority, indent=2, default=str), encoding="utf-8")
    print(f"Done in {time.time() - started:.0f}s")
    return {"role": role, "seniority": seniority}


if __name__ == "__main__":
    run_all()
