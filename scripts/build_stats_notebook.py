"""Build and EXECUTE notebooks/statistical_analysis.ipynb (outputs are real, saved in the file).

    python scripts/build_stats_notebook.py      # needs DATABASE_URL (read-only role)
"""

from pathlib import Path

import nbformat
from nbclient import NotebookClient

ROOT = Path(__file__).resolve().parents[1]
md, code = nbformat.v4.new_markdown_cell, nbformat.v4.new_code_cell

cells = [
    md("# Statistical analysis: AI Job Market & Interview Coach\n\n"
       "Data is read from **PostgreSQL** with the read-only role (`DATABASE_URL`). Two sources are analysed "
       "**separately** (never pooled): `data_jobs` 2023 (784,897 data-role postings) and the Arbeitnow API "
       "snapshot of 2026-10-08 (3,026 postings, all occupations).\n\n"
       "Principles: (1) every test states H0/H1, assumptions and an **effect size**: with hundreds of thousands "
       "of rows almost everything is 'significant'; (2) observational data: **associations, not causes**."),
    code("import json, os, sys\nimport pandas as pd\nfrom IPython.display import Image, display\n"
         "sys.path.insert(0, os.path.abspath('..'))\n"
         "from market.stats import analyses as A\nfrom market.stats import run_stats as R\n"
         "from market.stats.data import reference_jobs, live_jobs, reference_skill_matrix, query_df\n"
         "pd.set_option('display.width', 160); pd.set_option('display.max_columns', 20)\nR.style()\n"
         "ref, live = reference_jobs(), live_jobs()\nprint(ref.shape, live.shape)"),
    md("## 1. Descriptive statistics"),
    code("desc = A.descriptive_tables(ref, live)\n"
         "pd.DataFrame({'reference skill_count': desc['reference_skill_count'], 'reference salary (USD/yr)': desc['reference_salary_year'],\n"
         "              'live skill_count': desc['live_skill_count'], 'live description words': desc['live_description_words']})"),
    code("pd.DataFrame(desc['reference_skill_count_by_role']).T[['n','mean','sd','median','q1','q3','skewness']]"),
    code("pd.DataFrame(desc['live_skill_count_by_family']).T[['n','mean','sd','median','q1','q3','skewness']].sort_values('n', ascending=False)"),
    md("Skill counts are **right-skewed** (skewness > 0.9 in every group): rank-based tests are used for them."),
    md("## 2. Question A: do senior postings list more skills? (data_jobs 2023)\n"
       "- H0: within each role family, senior and non-senior skill-count distributions are equal.\n"
       "- H1: they differ (two-sided).\n- Test: Mann-Whitney U per role family (Holm correction); effect size Cliff's δ."),
    code("a = A.senior_skill_count_test(ref)\npd.DataFrame(a['results'])[['role_family','n_senior','n_non_senior','mean_senior','mean_non_senior',"
         "'mean_difference','mean_difference_ci95','p_holm','cliffs_delta','effect','prob_senior_lists_more']]"),
    code("R.fig_skill_count_by_seniority(ref, a)\ndisplay(Image(str(R.FIG_DIR / 'A_skill_count_by_seniority.png'), width=900))"),
    md("**Interpretation:** H0 is rejected for all three roles (p < 1e-40), but the effect is **small for Data Analysts "
       "and negligible for Data Engineers and Data Scientists**. A senior posting has only a 52-58% chance of listing more "
       "skills than a non-senior one. Seniority is not mainly expressed by a longer skill list."),
    md("## 3. Question B: is remote work associated with the job family?\n"
       "- H0: remote status is independent of role/job family. H1: it is not.\n"
       "- Test: Pearson chi-square of independence (expected-count rule checked); effect size Cramér's V. "
       "Run **separately** on each source."),
    code("b_ref = A.remote_association_test(ref, 'role_family', 'work_from_home', 'data_jobs 2023')\n"
         "b_live = A.remote_association_test(live, 'job_family', 'remote', 'Arbeitnow snapshot 2026')\n"
         "pd.DataFrame([{k: b[k] for k in ['question','n','chi2','dof','p_value','cramers_v','effect','assumptions']} for b in (b_ref, b_live)])"),
    code("R.fig_remote_share(ref, 'role_family', 'work_from_home', 'Remote share by role family (2023 reference data)', 'B_remote_by_role_reference', "
         "f\"Source: data_jobs 2023. Chi-square: Cramér's V = {b_ref['cramers_v']:.3f} ({b_ref['effect']}).\")\n"
         "R.fig_remote_share(live, 'job_family', 'remote', 'Remote share by job family (live API snapshot, Oct 2026)', 'B_remote_by_family_live', "
         "f\"Source: Arbeitnow API snapshot 2026-10-08. Chi-square: Cramér's V = {b_live['cramers_v']:.3f} ({b_live['effect']}).\")\n"
         "display(Image(str(R.FIG_DIR / 'B_remote_by_role_reference.png'), width=700)); display(Image(str(R.FIG_DIR / 'B_remote_by_family_live.png'), width=700))"),
    md("**Interpretation:** both tests reject independence, but in 2023 data roles the association is **negligible** "
       "(remote share 4.6-12.0% across roles). In the 2026 snapshot it is **small**: Marketing & Communication stands out "
       "(20.1% remote). The two sources are different populations, so the numbers are not compared over time."),
    md("## 4. Question C: which skills are over-represented in senior postings, within the same role?\n"
       "- For each skill: H0 common odds ratio = 1 across the three role strata; H1 ≠ 1.\n"
       "- Test: Cochran-Mantel-Haenszel (controls for role mix), Benjamini-Hochberg FDR 5%; effect size MH odds ratio."),
    code("skills = query_df('SELECT s.name FROM market.job_skills_reference js JOIN market.skills s USING (skill_id) GROUP BY s.name HAVING COUNT(*) >= %s', (5000,))['name'].tolist()\n"
         "c = A.senior_skill_association(ref, reference_skill_matrix(skills))\nres_c = pd.DataFrame(c['results'])\n"
         "print(c['data']); print('skills tested:', len(res_c), '| significant at 5% FDR:', int(res_c.significant_fdr_5pct.sum()),\n"
         "      '| heterogeneous across roles (Breslow-Day p<0.05):', int((res_c.homogeneity_p < 0.05).sum()))\n"
         "pd.concat([res_c.head(10), res_c.tail(5)])[['skill','senior_share_pct','non_senior_share_pct','mh_odds_ratio','or_ci95','q_value_bh','homogeneity_p']]"),
    code("R.fig_senior_odds_ratios(c)\ndisplay(Image(str(R.FIG_DIR / 'C_senior_skill_odds_ratios.png'), width=750))"),
    md("**Interpretation:** data-platform and cloud tools (Looker, Redshift, Snowflake, Airflow, Terraform, AWS, Kafka) are "
       "1.4-1.8× more likely (odds) to appear in senior postings of the same role; Excel, VBA, MATLAB and C++ are less likely. "
       "Many associations differ in strength between roles (Breslow-Day), so the pooled odds ratio is an average."),
    md("## 5. Question D: what is the advertised salary associated with? (statsmodels OLS)\n"
       "- Model: log(salary) ~ role family + senior + remote + skill count; US postings only (currency/country held constant); "
       "HC3 robust standard errors.\n- H0 for each coefficient: = 0."),
    code("d = A.salary_model(ref)\nprint(d['data']); print('R² =', d['r_squared'], '| adj. R² =', d['adj_r_squared'])\n"
         "print(json.dumps(d['assumptions'], indent=1))\npd.DataFrame(d['coefficients'])"),
    code("R.fig_salary_coefficients(d)\ndisplay(Image(str(R.FIG_DIR / 'D_salary_model.png'), width=750))"),
    md("**Interpretation:** holding the other terms constant, senior postings advertise about **17% more** "
       "(95% CI 15.9-18.4%), ML Engineer postings about 61% more than Data Analyst postings, remote postings about 3% more, "
       "and each additional listed skill about 0.3% more. The model explains 26% of the variance: most salary variation "
       "comes from factors not in the data (company, city, experience). Residual variance is not constant "
       "(Breusch-Pagan), which is why robust standard errors are used. Salaries are published by only 2.8% of postings, "
       "a possibly non-random subset."),
    md("## 6. Question E: do more experienced profiles list more skills? (live snapshot)\n"
       "- H0: equal skill-count distributions across employer-stated levels. Kruskal-Wallis + Spearman ρ.\n"
       "- Run overall **and within description language** (a confounder: the taxonomy detects more skills in English text)."),
    code("e = A.experience_skill_test(live)\nprint('English description share by level (%):', e['english_description_share_pct'])\n"
         "pd.DataFrame(e['results'])[['subset','n','means','kruskal_H','p_value','epsilon_squared','spearman_rho','spearman_p']]"),
    code("R.fig_experience_skills(live)\ndisplay(Image(str(R.FIG_DIR / 'E_experience_level_skills.png'), width=750))"),
    md("**Interpretation:** 'experienced' postings list the most skills; the relationship is **not monotonic** "
       "(lead/manager postings list fewer). The effect is clearer within English descriptions (ε² ≈ 0.09) than "
       "within German ones (ε² ≈ 0.01), consistent with the measurement limitation. Small sample (n = 1,616 labelled)."),
    md("## 7. Feature correlations (Spearman)"),
    code("corr = A.spearman_correlations(ref)\nR.fig_correlations(corr)\ndisplay(Image(str(R.FIG_DIR / 'F_feature_correlations.png'), width=650))\ncorr"),
    md("Total skills correlates with the per-type counts **by construction** (they are its parts). Salary correlates most "
       "with library (ρ = 0.25) and programming skills (0.20) and seniority (0.22), and negatively with analyst tools "
       "(-0.28, typical of lower-paid analyst roles). Correlations between dummy variables are approximate."),
    md("## 8. Limitations\n- Observational postings: associations only, no causal claims.\n"
       "- Reference data: 2023, data roles, collector's search locations; seniority label derived from titles; "
       "skills keyword-extracted by the dataset author.\n- Salary: 2.8% of postings, US-heavy, advertised (not actual) pay.\n"
       "- Live data: one week, Germany-centred, rule-based labels, English-oriented skill taxonomy.\n"
       "- Large n: p-values are uninformative on their own; read the effect sizes."),
]

nb = nbformat.v4.new_notebook(cells=cells, metadata={"kernelspec": {"name": "python3", "display_name": "Python 3 (coach)", "language": "python"}})
NotebookClient(nb, timeout=1200, kernel_name="python3", resources={"metadata": {"path": str(ROOT / "notebooks")}}).execute()
out = ROOT / "notebooks" / "statistical_analysis.ipynb"
nbformat.write(nb, out)
print("Executed and saved", out)
