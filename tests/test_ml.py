"""ML pipeline pieces on synthetic data (no database)."""

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression

from market.ml.data import Dataset, build_features
from market.ml.train import grouped_split, multiclass_metrics, predict_roles, stratified_subsample

SKILLS = ["AWS", "Excel", "Python", "SQL", "Tableau"]


def synthetic_dataset(n: int = 3000, seed: int = 0) -> Dataset:
    rng = np.random.default_rng(seed)
    roles = rng.choice(["Data Analyst", "Data Engineer"], n)
    lists = pd.Series([
        [s for s in SKILLS if rng.random() < (0.8 if (s in ("Excel", "Tableau")) == (r == "Data Analyst") else 0.15)]
        for r in roles])
    X = build_features(lists, SKILLS)
    return Dataset(X=X, y_role=pd.Series(roles), y_senior=pd.Series(rng.random(n) < 0.2),
                   groups=pd.Series(rng.integers(0, 300, n)), feature_skills=SKILLS)


def test_build_features_is_shared_by_training_and_inference():
    X = build_features(pd.Series([["Python", "SQL", "Kubernetes"], []]), SKILLS)
    assert list(X.columns) == [*SKILLS, "n_skills"]
    assert X.iloc[0].to_dict() == {"AWS": 0, "Excel": 0, "Python": 1, "SQL": 1, "Tableau": 0, "n_skills": 2}
    assert X.iloc[1].sum() == 0  # unknown skills (Kubernetes) are ignored, not an error


def test_grouped_split_never_shares_a_company():
    ds = synthetic_dataset()
    train, test = grouped_split(ds)
    assert len(train) + len(test) == len(ds.X)
    assert not set(ds.groups.iloc[train]) & set(ds.groups.iloc[test])
    assert 0.1 < len(test) / len(ds.X) < 0.3


def test_stratified_subsample_keeps_class_proportions():
    y = pd.Series(["a"] * 900 + ["b"] * 100)
    idx = stratified_subsample(y, 200)
    assert len(idx) == 200 and (y.iloc[idx] == "b").sum() == 20 and len(set(idx)) == 200


def test_metrics_and_prediction_on_learnable_signal():
    ds = synthetic_dataset()
    train, test = grouped_split(ds)
    model = LogisticRegression().fit(ds.X.iloc[train], ds.y_role.iloc[train])
    m = multiclass_metrics(ds.y_role.iloc[test], model.predict(ds.X.iloc[test]), sorted(ds.y_role.unique()))
    assert m["macro_f1"] > 0.8 and len(m["confusion_matrix"]) == 2 and set(m["per_class"]) == {"Data Analyst", "Data Engineer"}
    bundle = {"model": model, "feature_skills": SKILLS, "classes": list(model.classes_)}
    analyst = predict_roles(bundle, ["Excel", "Tableau", "SQL"])
    engineer = predict_roles(bundle, ["AWS", "Python"])
    assert analyst[0]["role_family"] == "Data Analyst" and engineer[0]["role_family"] == "Data Engineer"
    assert abs(sum(p["probability"] for p in predict_roles(bundle, ["SQL"], top=2)) - 1) < 1e-6
