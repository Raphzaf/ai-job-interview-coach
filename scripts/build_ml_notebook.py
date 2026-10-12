"""Build and EXECUTE notebooks/ml_analysis.ipynb from the saved ML results + the trained model.

    python scripts/build_ml_notebook.py      # after `python -m market.ml.train` (needs DATABASE_URL for the data overview)

Training itself (≈ minutes, CPU) runs in `market.ml.train`; the notebook loads its
JSON results and the saved model, shows every metric/figure, and runs live
predictions with the saved model, so its outputs are real and reproducible.
"""

from pathlib import Path

import nbformat
from nbclient import NotebookClient

ROOT = Path(__file__).resolve().parents[1]
md, code = nbformat.v4.new_markdown_cell, nbformat.v4.new_code_cell

cells = [
    md("# Machine learning: role-family classifier\n\n"
       "**Question:** given a skill profile, which data role family does a job posting belong to? "
       "This lets the interview coach position a candidate's CV against the market.\n\n"
       "**Data:** `lukebarousse/data_jobs` 2023, read from PostgreSQL. **Features:** the 58 skills of the coach's taxonomy "
       "(multi-hot) + number of skills: exactly what the coach can extract from a CV (train/serve consistency). Job titles are "
       "**never** used (the role label was derived from titles by the dataset author: leakage)."),
    code("import json, os, sys\nimport joblib, pandas as pd\nfrom IPython.display import Image, display\nsys.path.insert(0, os.path.abspath('..'))\n"
         "from market.ml.train import RESULTS_DIR, predict_roles\nfrom market.ml.figures import FIG_DIR\n"
         "pd.set_option('display.width', 160); pd.set_option('display.max_columns', 20)\n"
         "role = json.loads((RESULTS_DIR / 'role_model.json').read_text())\nsen = json.loads((RESULTS_DIR / 'seniority_experiment.json').read_text())\n"
         "{k: role[k] for k in ['rows','features','train_rows','test_rows','train_companies','test_companies','tuning_rows']}"),
    md("## 1. Split, class balance and baselines\nCompany-grouped 80/20 split (`GroupShuffleSplit`): no company appears in both sets, "
       "so templated postings from one employer cannot inflate the test score. Classes are imbalanced, so **macro-F1** is the main metric."),
    code("pd.DataFrame({'train': role['class_distribution_train'], 'test': role['class_distribution_test']}).assign(\n"
         "    test_share_pct=lambda d: (d.test / d.test.sum() * 100).round(2)).sort_values('train', ascending=False)"),
    code("pd.DataFrame({k: {m: v[m] for m in ['accuracy','balanced_accuracy','macro_f1','weighted_f1']} for k, v in role['baselines'].items()}).T"),
    md("## 2. Model selection (cross-validation on the training set only)\nStratifiedGroupKFold (3 folds) on a stratified subsample "
       "of the training set; grid search per candidate; selection by mean CV macro-F1."),
    code("pd.DataFrame([{'model': k, 'best_params': v['best_params'], 'cv_macro_f1': f\"{v['cv_macro_f1_mean']:.4f} ± {v['cv_macro_f1_std']:.4f}\"}\n"
         "              for k, v in role['candidates'].items()])"),
    code("for name, v in role['candidates'].items():\n    print(name); display(pd.DataFrame(v['cv_grid']).sort_values('macro_f1', ascending=False).head(4))"),
    md("## 3. Test-set evaluation (used once, all candidates reported)"),
    code("pd.DataFrame({k: {m: v['test'][m] for m in ['accuracy','balanced_accuracy','macro_f1','weighted_f1']} for k, v in role['candidates'].items()}).T"),
    code("display(Image(str(FIG_DIR / 'ML_model_comparison.png'), width=750))\nprint('Selected:', role['selected_model'], '-', role['selection_rule'])"),
    code("best = role['candidates'][role['selected_model']]['test']\npd.DataFrame(best['per_class']).T[['precision','recall','f1-score','support']]"),
    code("display(Image(str(FIG_DIR / 'ML_confusion_matrix.png'), width=650))"),
    md("## 4. Interpretation"),
    code("display(Image(str(FIG_DIR / 'ML_feature_importance.png'), width=650))"),
    code("pd.DataFrame({cls: {'most positive': ', '.join(f'{f} ({c:+.2f})' for f, c in d['positive']),\n"
         "                     'most negative': ', '.join(f'{f} ({c:+.2f})' for f, c in d['negative'])}\n"
         "              for cls, d in role['logistic_top_features'].items()}).T"),
    md("## 5. Using the saved model on CV skill lists\nThe coach extracts skills from a CV with the same taxonomy; `predict_roles` uses "
       "the same `build_features` function as training. The skill lists below come from the project's **fictional** example and "
       "evaluation CVs (extracted by the coach's real extractor)."),
    code("from app.matching.skills import extract_skills\nbundle = joblib.load(os.path.join('..', 'models', 'role_classifier.joblib'))\n"
         "cvs = {name: extract_skills(open(os.path.join('..', 'evaluation', 'data', f'{name}.txt')).read())\n"
         "       for name in ['cv_ml_engineer', 'cv_backend_developer', 'cv_marketing_coordinator']}\n"
         "pd.DataFrame([{'cv': n, 'skills_used_by_model': ', '.join(s for s in skills if s in bundle['feature_skills']),\n"
         "               'top_3_roles': '; '.join(f\"{p['role_family']} {p['probability']:.0%}\" for p in predict_roles(bundle, skills))}\n"
         "              for n, skills in cvs.items()])"),
    md("## 6. Secondary experiment: senior vs non-senior\nSame features + role one-hot, Data Analyst/Engineer/Scientist only, company-grouped split, "
       "class_weight='balanced'. Phase 4 showed skill differences between senior and non-senior postings are small, so a weak model is expected."),
    code("pd.DataFrame({k: {m: v[m] for m in ['best_params','cv_roc_auc','test_roc_auc','test_average_precision','test_balanced_accuracy','test_f1_senior']}\n"
         "              for k, v in sen['models'].items()}).T.assign(baseline_average_precision=sen['baseline']['average_precision'])"),
    code("display(Image(str(FIG_DIR / 'ML_seniority_roc.png'), width=450))"),
    md("## 7. Limitations\n- Labels come from the dataset author's title classifier (`job_title_short`), not from human annotation.\n"
       "- Skills were keyword-extracted by the author; only the 58 coach-taxonomy skills are used, so specialised tools outside the taxonomy are invisible to the model.\n"
       "- 2023 postings, data roles only, collector's search locations: the model describes this market, not every market.\n"
       "- A CV is not a job posting: predictions on CVs are a positioning signal, not a ground-truth label.\n"
       "- Hyper-parameters were tuned on a subsample (compute budget); results could improve slightly with full-data tuning."),
]

nb = nbformat.v4.new_notebook(cells=cells, metadata={"kernelspec": {"name": "python3", "display_name": "Python 3 (coach)", "language": "python"}})
NotebookClient(nb, timeout=1200, kernel_name="python3", resources={"metadata": {"path": str(ROOT / "notebooks")}}).execute()
nbformat.write(nb, ROOT / "notebooks" / "ml_analysis.ipynb")
print("Executed and saved notebooks/ml_analysis.ipynb")
