"""Skill extraction and normalisation with a curated taxonomy.

Why a taxonomy instead of asking the LLM "which skills match"?
- **Deterministic & explainable**: the same documents always give the same
  skills, and every detected skill can be pointed to in the text.
- **Normalisation**: "PostgreSQL", "Postgres" and "psql" are the same skill;
  "scikit-learn" and "sklearn" too. Aliases map to one canonical name so the
  CV/job overlap is not missed because of spelling.
- **No hallucinated skills**: a skill is only reported if its name (or an
  alias) literally appears in the document.

Limitation (documented in the README): skills that are not in the taxonomy are
not counted in the skill-overlap score. Requirement coverage (semantic, see
matcher.py) compensates for this partially.
"""

from __future__ import annotations

import re
from functools import lru_cache

from app.document_processing.cleaner import normalize_for_matching

# canonical name -> (category, aliases). Aliases are matched case-insensitively
# on word boundaries; the canonical name itself is always an alias.
SKILL_TAXONOMY: dict[str, tuple[str, list[str]]] = {
    # --- Programming languages ---
    "Python": ("Programming", ["python3"]),
    "Java": ("Programming", []),
    "JavaScript": ("Programming", ["js", "ecmascript"]),
    "TypeScript": ("Programming", []),
    "C++": ("Programming", ["cpp"]),
    "C#": ("Programming", ["csharp", "c sharp"]),
    "Go": ("Programming", ["golang"]),
    "Rust": ("Programming", []),
    "Scala": ("Programming", []),
    "Kotlin": ("Programming", []),
    "Swift": ("Programming", []),
    "PHP": ("Programming", []),
    "Ruby": ("Programming", []),
    "R": ("Programming", ["rstudio"]),
    "SQL": ("Data", ["t-sql", "pl/sql"]),
    "Bash": ("DevOps", ["shell scripting", "shell"]),
    # --- Machine learning / AI ---
    "Machine Learning": ("AI/ML", ["ml", "machine-learning"]),
    "Deep Learning": ("AI/ML", ["deep-learning", "neural networks", "neural network"]),
    "NLP": ("AI/ML", ["natural language processing", "text mining"]),
    "Computer Vision": ("AI/ML", ["image recognition", "opencv"]),
    "Generative AI": ("AI/ML", ["genai", "gen ai", "generative models"]),
    "LLMs": ("AI/ML", ["llm", "large language models", "large language model", "gpt", "chatgpt"]),
    "RAG": ("AI/ML", ["retrieval-augmented generation", "retrieval augmented generation"]),
    "Prompt Engineering": ("AI/ML", ["prompt design"]),
    "Fine-tuning": ("AI/ML", ["fine tuning", "finetuning", "lora", "peft"]),
    "Embeddings": ("AI/ML", ["embedding", "sentence embeddings", "vector embeddings"]),
    "Vector Databases": ("AI/ML", ["vector database", "vector db", "vector store", "faiss", "pinecone", "chroma", "chromadb", "weaviate", "qdrant", "milvus", "pgvector"]),
    "Transformers": ("AI/ML", ["hugging face", "huggingface", "transformer models", "bert"]),
    "LangChain": ("AI/ML", ["langgraph"]),
    "LlamaIndex": ("AI/ML", ["llama index", "llama-index"]),
    "PyTorch": ("AI/ML", ["torch"]),
    "TensorFlow": ("AI/ML", ["keras"]),
    "scikit-learn": ("AI/ML", ["sklearn", "scikit learn"]),
    "XGBoost": ("AI/ML", ["lightgbm", "gradient boosting", "catboost"]),
    "MLOps": ("AI/ML", ["mlflow", "model deployment", "model monitoring", "kubeflow"]),
    "Statistics": ("Data", ["statistical analysis", "statistical modeling", "hypothesis testing", "a/b testing"]),
    "Time Series": ("Data", ["forecasting", "time-series"]),
    "Recommender Systems": ("AI/ML", ["recommendation systems", "recommendation engine"]),
    # --- Data ---
    "Pandas": ("Data", []),
    "NumPy": ("Data", []),
    "Spark": ("Data", ["pyspark", "apache spark"]),
    "Airflow": ("Data", ["apache airflow"]),
    "dbt": ("Data", []),
    "Kafka": ("Data", ["apache kafka"]),
    "ETL": ("Data", ["data pipelines", "data pipeline", "elt"]),
    "Data Visualization": ("Data", ["data visualisation", "matplotlib", "seaborn", "plotly"]),
    "Power BI": ("Data", ["powerbi"]),
    "Tableau": ("Data", []),
    "Excel": ("Data", ["microsoft excel", "spreadsheets"]),
    "Data Analysis": ("Data", ["data analytics", "exploratory data analysis", "eda"]),
    "Snowflake": ("Data", []),
    "BigQuery": ("Data", ["big query"]),
    "Databricks": ("Data", []),
    # --- Databases ---
    "PostgreSQL": ("Databases", ["postgres", "psql"]),
    "MySQL": ("Databases", ["mariadb"]),
    "MongoDB": ("Databases", ["mongo"]),
    "Redis": ("Databases", []),
    "Elasticsearch": ("Databases", ["elastic search", "opensearch"]),
    "NoSQL": ("Databases", []),
    # --- Web / backend ---
    "FastAPI": ("Backend", []),
    "Flask": ("Backend", []),
    "Django": ("Backend", []),
    "Node.js": ("Backend", ["nodejs", "Node"]),
    "Spring": ("Backend", ["spring boot"]),
    "REST APIs": ("Backend", ["rest api", "rest apis", "restful", "REST", "api development"]),
    "GraphQL": ("Backend", []),
    "Microservices": ("Backend", ["microservice"]),
    "React": ("Frontend", ["react.js", "reactjs"]),
    "Angular": ("Frontend", []),
    "Vue.js": ("Frontend", ["vue", "vuejs"]),
    "HTML/CSS": ("Frontend", ["html", "css", "html5", "css3"]),
    "Streamlit": ("Frontend", []),
    # --- Cloud / DevOps ---
    "AWS": ("Cloud", ["amazon web services", "sagemaker", "aws lambda", "ec2", "s3"]),
    "Azure": ("Cloud", ["microsoft azure"]),
    "GCP": ("Cloud", ["google cloud", "google cloud platform", "vertex ai"]),
    "Docker": ("DevOps", ["containers", "containerization", "containerisation"]),
    "Kubernetes": ("DevOps", ["k8s"]),
    "Terraform": ("DevOps", ["infrastructure as code"]),
    "CI/CD": ("DevOps", ["ci / cd", "continuous integration", "continuous deployment", "github actions", "gitlab ci", "jenkins"]),
    "Git": ("DevOps", ["github", "gitlab", "version control"]),
    "Linux": ("DevOps", ["unix"]),
    "Testing": ("Engineering", ["unit testing", "pytest", "test-driven development", "tdd", "automated testing"]),
    # --- Methods / soft skills ---
    "Agile": ("Methods", ["scrum", "kanban"]),
    "Project Management": ("Methods", ["project manager"]),
    "Communication": ("Soft skills", ["communication skills", "presenting", "presented", "presentations", "presentation skills", "stakeholder communication"]),
    "Leadership": ("Soft skills", ["team lead", "led a team", "mentoring", "mentored", "mentor"]),
    "Teamwork": ("Soft skills", ["collaboration", "cross-functional", "team player"]),
    "Problem Solving": ("Soft skills", ["problem-solving", "analytical skills"]),
    "Stakeholder Management": ("Soft skills", ["stakeholders", "stakeholder"]),
    "English": ("Languages", []),
    "French": ("Languages", []),
    "Spanish": ("Languages", []),
    "German": ("Languages", []),
    # --- Marketing / business (so non-tech CVs are also handled) ---
    "SEO": ("Marketing", ["search engine optimization", "search engine optimisation"]),
    "Content Marketing": ("Marketing", ["content strategy", "copywriting"]),
    "Social Media": ("Marketing", ["social media marketing", "instagram", "tiktok", "linkedin ads"]),
    "Google Analytics": ("Marketing", ["ga4"]),
    "CRM": ("Marketing", ["salesforce", "hubspot"]),
    "Email Marketing": ("Marketing", ["mailchimp", "newsletters"]),
}

# Skill hierarchy: having the key skill implies the listed broader skills.
# Kept deliberately small and uncontroversial (a specialisation implies its
# field, a framework implies its language), so it never invents expertise.
SKILL_IMPLICATIONS: dict[str, list[str]] = {
    "RAG": ["Generative AI", "LLMs"],
    "LLMs": ["Generative AI"],
    "Fine-tuning": ["Machine Learning"],
    "Deep Learning": ["Machine Learning"],
    "NLP": ["Machine Learning"],
    "Computer Vision": ["Machine Learning"],
    "PyTorch": ["Deep Learning"],
    "TensorFlow": ["Deep Learning"],
    "scikit-learn": ["Machine Learning", "Python"],
    "Pandas": ["Python"],
    "Django": ["Python"],
    "Flask": ["Python"],
    "FastAPI": ["Python", "REST APIs"],
    "PostgreSQL": ["SQL"],
    "MySQL": ["SQL"],
    "Node.js": ["JavaScript"],
    "React": ["JavaScript"],
    "Vue.js": ["JavaScript"],
}

# Aliases that are ordinary English words or letters: they are matched
# case-sensitively, so "R" or "Go" the language is found but "go to market" or
# "r&d" are not. Everything else is matched case-insensitively.
CASE_SENSITIVE_ALIASES = {"R", "Go", "REST", "Rust", "Swift", "Spring", "Excel", "Node"}


def _alias_pattern(alias: str) -> str:
    # Custom boundaries instead of \b: \b fails around "+", "#" and "." so
    # "C++", "C#" and "Node.js" would never match. The trailing look-ahead also
    # accepts a sentence-ending period ("...and Python.").
    return rf"(?<![\w+#/.-]){re.escape(alias)}(?![\w+#/&]|-\w|\.\w)"


@lru_cache
def _compiled_patterns() -> list[tuple[str, re.Pattern[str], bool]]:
    patterns: list[tuple[str, re.Pattern[str], bool]] = []
    for canonical, (_category, aliases) in SKILL_TAXONOMY.items():
        for alias in {canonical, *aliases}:
            case_sensitive = alias in CASE_SENSITIVE_ALIASES
            target = alias if case_sensitive else alias.lower()
            patterns.append((canonical, re.compile(_alias_pattern(target)), case_sensitive))
    return patterns


def normalize_skill(name: str) -> str | None:
    """Map any alias/spelling to its canonical skill name (None if unknown)."""
    lowered = name.strip().lower()
    for canonical, (_category, aliases) in SKILL_TAXONOMY.items():
        if lowered == canonical.lower() or lowered in (a.lower() for a in aliases):
            return canonical
    return None


def skill_category(canonical: str) -> str:
    return SKILL_TAXONOMY.get(canonical, ("Other", []))[0]


def find_skill_mentions(text: str) -> list[tuple[int, int, str]]:
    """All (start, end, canonical) skill mentions, sorted by position.

    Positions refer to `text` (lower-casing keeps the length unchanged for
    the cleaned Latin-script text we process).
    """
    lowered = text.lower()
    mentions: list[tuple[int, int, str]] = []
    for canonical, pattern, case_sensitive in _compiled_patterns():
        for m in pattern.finditer(text if case_sensitive else lowered):
            mentions.append((m.start(), m.end(), canonical))
    return sorted(mentions)


_ALTERNATIVE_SEPARATOR = re.compile(r"^\s*,?\s*(?:or|/|and/or)\s*$", re.IGNORECASE)


def alternative_groups(text: str) -> list[set[str]]:
    """Groups of skills offered as alternatives: "PyTorch or TensorFlow", "FastAPI/Flask".

    A candidate who has ONE of them satisfies the requirement, so the other
    should not be reported as a missing skill.
    """
    mentions = find_skill_mentions(text)
    groups: list[set[str]] = []
    for (s1, e1, a), (s2, _e2, b) in zip(mentions, mentions[1:]):
        if a != b and s2 >= e1 and _ALTERNATIVE_SEPARATOR.match(text[e1:s2]):
            if groups and a in groups[-1]:
                groups[-1].add(b)
            else:
                groups.append({a, b})
    return groups


def extract_skills(text: str) -> list[str]:
    """Return canonical skills mentioned in `text`, in taxonomy order (stable output)."""
    lowered = normalize_for_matching(text)
    original = text.replace("\n", " ")
    found: set[str] = set()
    for canonical, pattern, case_sensitive in _compiled_patterns():
        if canonical in found:
            continue
        haystack = original if case_sensitive else lowered
        if pattern.search(haystack):
            found.add(canonical)
    return [skill for skill in SKILL_TAXONOMY if skill in found]


def expand_implied(skills: list[str]) -> set[str]:
    """Add the broader skills implied by `skills` (transitively)."""
    result = set(skills)
    frontier = list(skills)
    while frontier:
        for implied in SKILL_IMPLICATIONS.get(frontier.pop(), []):
            if implied not in result:
                result.add(implied)
                frontier.append(implied)
    return result
