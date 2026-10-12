"""Feature matrix for the ML models (read from PostgreSQL, read-only role).

Train/serve consistency: features are ONLY the skills of the interview coach's
taxonomy (`skills.in_coach_taxonomy`). Those are exactly the skills the coach
can extract from a CV, so the trained model can later be applied to a
candidate's CV without silently missing features (a model that relied on,
say, 'hadoop' could never see it at inference time).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from market.stats.data import query_df

FEATURE_SKILLS_SQL = """
SELECT s.name
FROM market.skills s
JOIN market.job_skills_reference js ON js.skill_id = s.skill_id
WHERE s.in_coach_taxonomy
GROUP BY s.name
HAVING COUNT(*) >= %s
ORDER BY s.name
"""

JOBS_SQL = """
SELECT job_id, role_family, is_senior, company_id
FROM market.jobs_reference
WHERE NOT skills_missing
"""

LINKS_SQL = """
SELECT js.job_id, s.name AS skill
FROM market.job_skills_reference js JOIN market.skills s ON s.skill_id = js.skill_id
WHERE s.name = ANY(%s)
"""


@dataclass
class Dataset:
    X: pd.DataFrame          # one 0/1 column per feature skill + 'n_skills'
    y_role: pd.Series        # role family
    y_senior: pd.Series      # bool
    groups: pd.Series        # company id (for leakage-safe splitting)
    feature_skills: list[str]


def build_features(skill_lists: pd.Series, feature_skills: list[str]) -> pd.DataFrame:
    """Turn lists of canonical skill names into the model's feature columns.

    Used for training (postings) AND inference (a CV's extracted skills), so
    both go through the same code path.
    """
    index = {s: i for i, s in enumerate(feature_skills)}
    matrix = np.zeros((len(skill_lists), len(feature_skills)), dtype=np.float32)
    for row, skills in enumerate(skill_lists):
        for s in skills:
            if s in index:
                matrix[row, index[s]] = 1.0
    X = pd.DataFrame(matrix, columns=feature_skills, index=skill_lists.index)
    X["n_skills"] = matrix.sum(axis=1)
    return X


def load_dataset(min_postings: int = 500) -> Dataset:
    feature_skills = query_df(FEATURE_SKILLS_SQL, (min_postings,))["name"].tolist()
    jobs = query_df(JOBS_SQL).set_index("job_id")
    links = query_df(LINKS_SQL, (feature_skills,))
    skill_lists = links.groupby("job_id")["skill"].agg(list)
    # Postings with no taxonomy skill carry no signal for this model and do not
    # resemble a CV input: they are excluded (count documented in the results).
    jobs = jobs.loc[jobs.index.intersection(skill_lists.index)].sort_index()
    X = build_features(skill_lists.reindex(jobs.index), feature_skills)
    groups = jobs["company_id"].fillna(-1).astype(int)
    # Postings without a company get their own group each (no shared identity).
    missing = groups == -1
    groups[missing] = -np.arange(1, missing.sum() + 1)
    return Dataset(X=X, y_role=jobs["role_family"], y_senior=jobs["is_senior"].astype(bool),
                   groups=groups, feature_skills=feature_skills)
