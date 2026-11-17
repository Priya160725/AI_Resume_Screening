import os
import io
import csv
import json
import re
import secrets
import hashlib
from html import escape
from importlib.metadata import version, PackageNotFoundError
import pymupdf
import mysql.connector
from docx import Document
from dotenv import load_dotenv
from flask_wtf.csrf import CSRFProtect
from flask import (
    Flask, request, redirect, url_for, flash,
    render_template_string, make_response,
)
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from werkzeug.utils import secure_filename
# ===================== CONFIGURATION =====================
load_dotenv()
app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY")
app.config["WTF_CSRF_ENABLED"] = True
app.config["WTF_CSRF_TIME_LIMIT"] = 3600

csrf = CSRFProtect(app)

if not app.secret_key:
    raise RuntimeError("FLASK_SECRET_KEY is missing. Add it to your .env file.")
MYSQL_HOST = os.getenv("MYSQL_HOST", "localhost")
MYSQL_USER = os.getenv("MYSQL_USER", "root")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "")
MYSQL_DATABASE = os.getenv("MYSQL_DATABASE", "ai_resume_screening")
ALLOWED_EXTENSIONS = {"pdf", "docx", "txt"}
MAX_RESUME_SIZE = 5 * 1024 * 1024
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024


@app.errorhandler(413)
def request_entity_too_large(error):
    return """
    <h1>Upload too large</h1>
    <p>The total upload size must not exceed 50 MB.</p>
    <a href="/">Return to Home</a>
    """, 413
# ===================== DATABASE =====================
def get_db_connection():
    return mysql.connector.connect(
        host=MYSQL_HOST, user=MYSQL_USER, password=MYSQL_PASSWORD,
        database=MYSQL_DATABASE, connection_timeout=10,
    )
def initialize_database():
    connection = cursor = None
    try:
        connection = get_db_connection()
        cursor = connection.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS screening_results (
                id INT AUTO_INCREMENT PRIMARY KEY,
                candidate_name VARCHAR(255) NOT NULL,
                filename VARCHAR(255) NOT NULL,
                job_title VARCHAR(255) NOT NULL,
                match_score FLOAT NOT NULL DEFAULT 0,
                similarity_score FLOAT NOT NULL DEFAULT 0,
                skill_score FLOAT NOT NULL DEFAULT 0,
                matching_skills TEXT,
                missing_skills TEXT,
                explanation TEXT,
                skill_evidence LONGTEXT NULL,
                resume_hash CHAR(64) NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        connection.commit()
        cursor.execute("""
            SELECT COUNT(*) FROM information_schema.columns
            WHERE table_schema = %s AND table_name = 'screening_results'
              AND column_name = 'skill_evidence'
        """, (MYSQL_DATABASE,))

        if cursor.fetchone()[0] == 0:
            cursor.execute(
                "ALTER TABLE screening_results ADD COLUMN skill_evidence LONGTEXT NULL"
            )
            connection.commit()


        cursor.execute("""
            SELECT COUNT(*) FROM information_schema.columns
            WHERE table_schema = %s AND table_name = 'screening_results'
              AND column_name = 'resume_hash'
        """, (MYSQL_DATABASE,))

        if cursor.fetchone()[0] == 0:
            cursor.execute(
                "ALTER TABLE screening_results ADD COLUMN resume_hash CHAR(64) NULL"
            )
            connection.commit()

        # Check the duplicate-detection index independently
        cursor.execute("""
            SELECT COUNT(*) FROM information_schema.statistics
            WHERE table_schema = %s
              AND table_name = 'screening_results'
              AND index_name = 'idx_resume_hash_job'
        """, (MYSQL_DATABASE,))

        if cursor.fetchone()[0] == 0:
            cursor.execute("""
                CREATE INDEX idx_resume_hash_job
                ON screening_results (resume_hash, job_title)
            """)
            connection.commit()


        cursor.execute("""
            CREATE TABLE IF NOT EXISTS candidate_progress_access (
                candidate_id INT PRIMARY KEY,
                access_token CHAR(64) NOT NULL UNIQUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS candidate_skill_progress (
                id BIGINT AUTO_INCREMENT PRIMARY KEY,
                candidate_id INT NOT NULL,
                skill VARCHAR(255) NOT NULL,
                status VARCHAR(20) NOT NULL DEFAULT 'Not Started',
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                UNIQUE KEY uq_candidate_skill (candidate_id, skill),
                INDEX idx_progress_candidate (candidate_id)
            )
        """)

        connection.commit()
    finally:
        if cursor is not None:
            cursor.close()
        if connection is not None and connection.is_connected():
            connection.close()
# ===================== RESUME EXTRACTION =====================
def safe_csv_cell(value):
    """Protect CSV exports from spreadsheet formula injection."""
    if value is None:
        return ""

    text = str(value)

    if text.lstrip(" \t\r\n").startswith(("=", "+", "-", "@")):
        return "'" + text

    return text


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def extract_resume_text(file_storage):
    filename = secure_filename(file_storage.filename)

    if not filename or not allowed_file(filename):
        raise ValueError("Unsupported file. Upload a PDF, DOCX or TXT file.")

    file_bytes = file_storage.read()
    file_storage.stream.seek(0)

    if not file_bytes:
        raise ValueError("The uploaded resume is empty.")

    if len(file_bytes) > MAX_RESUME_SIZE:
        raise ValueError("Resume is too large. Maximum size per resume is 5 MB.")

    extension = filename.rsplit(".", 1)[1].lower()

    # PDF extraction
    if extension == "pdf":
        if not file_bytes.startswith(b"%PDF-"):
            raise ValueError("Invalid PDF file. The file content does not match PDF format.")

        try:
            with pymupdf.open(stream=file_bytes, filetype="pdf") as pdf:
                return "\n".join(page.get_text() for page in pdf)

        except Exception as error:
            raise ValueError("Could not read this PDF. Check whether it is valid.") from error

    # DOCX extraction
    if extension == "docx":
        if not file_bytes.startswith(b"PK"):
            raise ValueError("Invalid DOCX file. The file content does not match DOCX format.")

        try:
            document = Document(io.BytesIO(file_bytes))
            parts = [p.text for p in document.paragraphs]

            for table in document.tables:
                for row in table.rows:
                    parts.append(" ".join(cell.text for cell in row.cells))

            return "\n".join(parts)

        except Exception as error:
            raise ValueError("Could not read this DOCX file. Check whether it is valid.") from error

    # TXT extraction
    if extension == "txt":
        try:
            return file_bytes.decode("utf-8-sig")

        except UnicodeDecodeError as error:
            raise ValueError("TXT file must use UTF-8 encoding.") from error

    raise ValueError("Unsupported file format.")

def guess_candidate_name(filename, resume_text):
    excluded = {
        "resume", "curriculum vitae", "curriculum", "vitae", "profile",
        "professional summary", "career objective", "education", "work experience",
        "contact", "contact information", "technical skills", "personal details",
        "projects", "skills", "objective", "summary", "experience", "certifications",
    }
    lines = [re.sub(r"\s+", " ", line).strip() for line in (resume_text or "").splitlines() if line.strip()]
    for line in lines[:5]:
        lowered = line.lower()
        if any(marker in lowered for marker in ("@", "www.", "http://", "https://", "linkedin", "github", "phone", "mobile", "email", "address:", "portfolio")):
            continue
        cleaned = re.sub(r"[^A-Za-z .'-]", "", line).strip()
        words = cleaned.split()
        if not 2 <= len(words) <= 4 or len(cleaned) > 60:
            continue
        if " ".join(words).lower() in excluded or any(w.lower() in excluded for w in words):
            continue
        if not all(re.fullmatch(r"[A-Za-z][A-Za-z.'-]*", word) for word in words):
            continue
        if any(w.lower() in {"developer", "engineer", "student", "analyst", "manager", "designer", "intern", "objective", "summary", "experience"} for w in words):
            continue
        return cleaned[:255]
    name = os.path.splitext(os.path.basename(filename or ""))[0]
    name = re.sub(r"[_-]+", " ", name)
    name = re.sub(r"\b(resume|cv|curriculum vitae)\b", "", name, flags=re.I)
    name = re.sub(r"\s+", " ", name).strip(" .-_")
    return name[:255] or "Unknown Candidate"
# ===================== SKILLS AND SCORING =====================

# ===================== SKILLS AND SCORING =====================

SKILL_ALIASES = {
    "nlp": "natural language processing",
    "natural-language processing": "natural language processing",
    "natural language processing (nlp)": "natural language processing",
    "ml": "machine learning",
    "llm": "large language models",
"large language model": "large language models",
    "ai": "artificial intelligence",
    "js": "javascript",
    "ts": "typescript",
    "py": "python",
    "c plus plus": "c++",
    "c sharp": "c#",
    "react.js": "react",
    "node": "node.js",
    "express": "express.js",
    "postgres": "postgresql",
    "mongo": "mongodb",
    "sklearn": "scikit-learn",
    "scikit learn": "scikit-learn",
    "powerbi": "power bi",
    "gcp": "google cloud",
    "google cloud platform": "google cloud",
    "amazon web services": "aws",
    "microsoft azure": "azure",
    "restful api": "rest api",
    "ci cd": "ci/cd",
    "continuous integration": "ci/cd",
    "continuous deployment": "ci/cd",
    "oop": "object oriented programming",
    "object-oriented programming": "object oriented programming",
}


def canonicalize_skill_name(skill):
    """Return one standard display name for known skill aliases."""
    cleaned = re.sub(r"\s+", " ", str(skill or "").strip().casefold())
    return SKILL_ALIASES.get(cleaned, cleaned)


def canonicalize_skill_list(skills):
    """Normalize aliases and remove duplicate skill labels."""
    result = []
    seen = set()

    for skill in skills or []:
        canonical = canonicalize_skill_name(skill)

        if canonical and canonical not in seen:
            result.append(canonical)
            seen.add(canonical)

    return result


SKILL_LIST = [
    # Programming languages
    "python", "java", "javascript", "js", "typescript", "ts",
"c", "c++", "c#",
    "php", "ruby", "go", "rust", "kotlin", "swift", "r", "scala",

    # Web development
    "html", "css", "react", "angular", "vue", "node.js", "express.js",
    "flask", "django", "fastapi", "spring boot", "bootstrap",
    "tailwind css", "next.js", "rest api", "graphql",

    # Databases
   "mysql", "sql", "nosql", "postgresql", "mongodb", "sqlite", "redis",
    "oracle database", "database management",

    # AI, machine learning and data science
    "machine learning", "ml", "deep learning", "artificial intelligence",
    "nlp", "natural language processing", "generative ai",
    "large language models", "llm", "computer vision",
    "tensorflow", "pytorch", "scikit-learn", "pandas", "numpy",
    "matplotlib", "seaborn", "data analysis", "data visualization",
    "data science", "statistics", "power bi", "tableau", "excel",

    # Cloud and DevOps
    "git", "github", "gitlab", "docker", "kubernetes", "aws",
    "azure", "google cloud", "linux", "jenkins", "terraform",
    "ci/cd", "devops",

    # Computer science fundamentals
    "data structures", "algorithms", "object oriented programming",
    "operating systems", "computer networks", "cybersecurity",
    "software engineering", "software testing", "unit testing",
    "agile", "scrum", "api testing",

    # Professional skills
    "communication", "leadership", "teamwork", "problem solving",
    "critical thinking", "project management", "time management",
]

def extract_skills(text):
    """Extract recognized skills and normalize aliases."""
    text_lower = (text or "").lower()
    found = []
    for skill in sorted(set(SKILL_LIST) | set(SKILL_ALIASES), key=len, reverse=True):
        if skill in ("js", "ts"):
            pattern = r"(?<![\w.])" + re.escape(skill.lower()) + r"(?!\w)"
        elif skill == "c":
            pattern = r"(?<!\w)c(?![\w+#])"
        else:
            pattern = r"(?<!\w)" + re.escape(skill.lower()) + r"(?!\w)"
        if re.search(pattern, text_lower):
            found.append(skill)

    return sorted(set(canonicalize_skill_list(found)))

def find_skill_evidence(resume_text, skills):
    """Return real resume sentences supporting recognized skills."""
    evidence = {}
    sentences = re.split(r"(?<=[.!?])\s+|\n+", resume_text or "")

    for skill in canonicalize_skill_list(skills):
        aliases = {skill}

        # Include all aliases for the canonical skill.
        for alias, canonical in SKILL_ALIASES.items():
            if canonicalize_skill_name(alias) == skill:
                aliases.add(alias)

        patterns = []

        for alias in aliases:
            if alias in ("js", "ts"):
                pattern = r"(?<![\w.])" + re.escape(alias.lower()) + r"(?!\w)"
            else:
                pattern = r"(?<!\w)" + re.escape(alias.lower()) + r"(?!\w)"

            patterns.append(pattern)

        snippets = []

        for sentence in sentences:
            clean = re.sub(r"\s+", " ", sentence).strip()

            if clean and any(
                re.search(pattern, clean.lower())
                for pattern in patterns
            ):
                snippets.append(clean[:300])

            if len(snippets) >= 3:
                break

        if snippets:
            evidence[skill] = snippets

    return evidence

def calculate_match(resume_text, job_description):
    """Calculate resume match using TF-IDF and required skill coverage."""
    resume_text = resume_text or ""
    job_description = job_description or ""

    resume_skills = extract_skills(resume_text)
    required_skills = extract_skills(job_description)

    similarity = 0.0

    if resume_text.strip() and job_description.strip():
        try:
            vectorizer = TfidfVectorizer(
                stop_words="english",
                ngram_range=(1, 2)
            )

            matrix = vectorizer.fit_transform(
                [resume_text, job_description]
            )

            similarity = (
                float(cosine_similarity(matrix[0:1], matrix[1:2])[0][0])
                * 100
            )

        except ValueError:
            similarity = 0.0

    if required_skills:
        matching = [
            skill for skill in required_skills
            if skill in resume_skills
        ]

        missing = [
            skill for skill in required_skills
            if skill not in resume_skills
        ]

        skill_score = len(matching) / len(required_skills) * 100
        overall = 0.4 * similarity + 0.6 * skill_score
    else:
        matching = []
        missing = []
        skill_score = 0.0
        overall = 0.4 * similarity + 0.6 * skill_score

    return {
        "match_score": round(max(0, min(100, overall)), 2),
        "similarity_score": round(max(0, min(100, similarity)), 2),
        "skill_score": round(max(0, min(100, skill_score)), 2),
        "matching_skills": matching,
        "missing_skills": missing,
        "skill_evidence": find_skill_evidence(resume_text, matching),
    }

# ===================== DATABASE OPERATIONS =====================
def is_duplicate_resume(resume_hash, job_title):
    connection = cursor = None
    try:
        connection = get_db_connection()
        cursor = connection.cursor()
        cursor.execute("""
            SELECT id FROM screening_results
            WHERE resume_hash = %s
            AND LOWER(job_title) = LOWER(%s)
            LIMIT 1
        """, (resume_hash, job_title))
        return cursor.fetchone() is not None
    finally:
        if cursor is not None:
            cursor.close()
        if connection is not None and connection.is_connected():
            connection.close()
def save_candidate(candidate):
    connection = cursor = None
    try:
        connection = get_db_connection()
        cursor = connection.cursor()
        cursor.execute("""
    INSERT INTO screening_results
    (candidate_name, filename, job_title, match_score, similarity_score,
     skill_score, matching_skills, missing_skills, explanation, skill_evidence, resume_hash)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
""", (
    candidate["candidate_name"],
    candidate["filename"],
    candidate["job_title"],
    candidate["match_score"],
    candidate["similarity_score"],
    candidate["skill_score"],
    json.dumps(candidate["matching_skills"]),
    json.dumps(candidate["missing_skills"]),
    candidate["explanation"],
    json.dumps(candidate.get("skill_evidence", {}), ensure_ascii=False),
    candidate["resume_hash"],
))
        connection.commit()
        return cursor.lastrowid
    finally:
        if cursor is not None:
            cursor.close()
        if connection is not None and connection.is_connected():
            connection.close()
def _decode_skills(candidate):
    """Decode saved JSON and normalize aliases in memory without writing to MySQL."""
    if candidate:
        for field in ("matching_skills", "missing_skills"):
            try:
                value = candidate.get(field) or "[]"
                decoded = json.loads(value) if isinstance(value, str) else value
                candidate[field] = canonicalize_skill_list(decoded if isinstance(decoded, list) else [])
            except (TypeError, json.JSONDecodeError):
                candidate[field] = []
        try:
            evidence = candidate.get("skill_evidence") or {}
            if isinstance(evidence, str):
                evidence = json.loads(evidence) if evidence.strip() else {}
            if not isinstance(evidence, dict):
                evidence = {}
            normalized_evidence = {}
            for key, values in evidence.items():
                canonical_key = canonicalize_skill_name(key)
                if isinstance(values, str):
                    values = [values]
                if isinstance(values, list):
                    normalized_evidence.setdefault(canonical_key, [])
                    for value in values:
                        if value and value not in normalized_evidence[canonical_key]:
                            normalized_evidence[canonical_key].append(str(value))
            candidate["skill_evidence"] = normalized_evidence
        except (TypeError, json.JSONDecodeError):
            candidate["skill_evidence"] = {}

        # Correct displayed scores after de-duplication; saved database rows are unchanged.
        matching = candidate.get("matching_skills", [])
        missing = candidate.get("missing_skills", [])
        required_count = len(set(matching + missing))
        if required_count:
            corrected_skill_score = len(matching) / required_count * 100
            similarity = float(candidate.get("similarity_score") or 0)
            candidate["skill_score"] = round(corrected_skill_score, 2)
            candidate["match_score"] = round(0.4 * similarity + 0.6 * corrected_skill_score, 2)
    return candidate

def get_candidates():
    connection = cursor = None
    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        cursor.execute("SELECT * FROM screening_results ORDER BY created_at DESC, id DESC")
        return [_decode_skills(c) for c in cursor.fetchall()]
    finally:
        if cursor is not None:
            cursor.close()
        if connection is not None and connection.is_connected():
            connection.close()
def get_candidate(candidate_id):
    connection = cursor = None
    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        cursor.execute("SELECT * FROM screening_results WHERE id = %s", (candidate_id,))
        return _decode_skills(cursor.fetchone())
    finally:
        if cursor is not None:
            cursor.close()
        if connection is not None and connection.is_connected():
            connection.close()
# ===================== SKILL GAP ANALYZER =====================
# Transparent, rule-based learning recommendations. No external AI/API is claimed.
SKILL_GAP_GUIDE = {
    "data structures": {"level": "Beginner to intermediate", "category": "Core computer science", "topics": ["Arrays and strings", "Linked lists, stacks and queues", "Trees, graphs and hash maps", "Time and space complexity"], "project": "Build a contact manager using lists, dictionaries and search", "resource": "https://www.geeksforgeeks.org/data-structures/"},
    "algorithms": {"level": "Intermediate", "category": "Problem solving", "topics": ["Searching and sorting", "Two pointers and recursion", "Greedy algorithms and dynamic programming", "Big-O analysis"], "project": "Create a visual sorting and searching demonstrator", "resource": "https://www.geeksforgeeks.org/fundamentals-of-algorithms/"},
    "natural language processing": {"level": "Intermediate", "category": "AI and language", "topics": ["Text cleaning and tokenization", "Stop words and stemming or lemmatization", "TF-IDF and text classification", "Word embeddings and evaluation"], "project": "Build a review sentiment or text classification app", "resource": "https://www.nltk.org/book/"},
    "nlp": {"level": "Intermediate", "category": "AI and language", "topics": ["Text cleaning and tokenization", "Stop words and stemming or lemmatization", "TF-IDF and text classification", "Word embeddings and evaluation"], "project": "Build a review sentiment or text classification app", "resource": "https://www.nltk.org/book/"},
    "rest api": {"level": "Beginner to intermediate", "category": "Backend development", "topics": ["HTTP methods and status codes", "JSON request and response", "Flask routes and request validation", "API testing and error handling"], "project": "Build a Flask REST API for a task manager", "resource": "https://flask.palletsprojects.com/en/stable/"},
    "flask": {"level": "Beginner to intermediate", "category": "Backend development", "topics": ["Routes and templates", "Forms and request handling", "Database integration", "REST endpoints and deployment basics"], "project": "Build a Flask CRUD application", "resource": "https://flask.palletsprojects.com/en/stable/"},
    "python": {"level": "Beginner to intermediate", "category": "Programming", "topics": ["Variables, conditions and loops", "Functions and modules", "OOP and exception handling", "File handling and packages"], "project": "Build a command-line expense tracker", "resource": "https://docs.python.org/3/tutorial/"},
    "mysql": {"level": "Beginner to intermediate", "category": "Database", "topics": ["SELECT, WHERE and ORDER BY", "JOIN and aggregate functions", "Primary and foreign keys", "Indexes and transactions"], "project": "Design a student course registration database", "resource": "https://dev.mysql.com/doc/"},
    "sql": {"level": "Beginner", "category": "Database", "topics": ["SELECT and filtering", "JOIN and GROUP BY", "Subqueries", "Insert, update and delete safely"], "project": "Create a library database and reporting queries", "resource": "https://www.w3schools.com/sql/"},
    "git": {"level": "Beginner", "category": "Developer tools", "topics": ["Repositories and commits", "Branches and merges", "Resolving conflicts", "Working with remote repositories"], "project": "Track a small Python project with meaningful commits", "resource": "https://git-scm.com/book/en/v2"},
    "github": {"level": "Beginner", "category": "Developer tools", "topics": ["Create repositories", "Push and pull changes", "README and .gitignore", "Issues and pull requests"], "project": "Publish a Python project with README and setup instructions", "resource": "https://docs.github.com/en/get-started"},
    "machine learning": {"level": "Intermediate", "category": "AI and data", "topics": ["Train, validation and test sets", "Regression and classification", "Feature preprocessing", "Metrics and overfitting"], "project": "Train and evaluate a student performance prediction model", "resource": "https://scikit-learn.org/stable/tutorial/index.html"},
    "scikit-learn": {"level": "Intermediate", "category": "AI and data", "topics": ["Estimators and fit/predict", "Preprocessing pipelines", "Model evaluation", "Cross-validation and tuning"], "project": "Compare two classifiers on a public dataset", "resource": "https://scikit-learn.org/stable/tutorial/index.html"},
    "javascript": {"level": "Beginner to intermediate", "category": "Frontend", "topics": ["Variables and functions", "DOM manipulation", "Events and form validation", "Fetch API and asynchronous code"], "project": "Build an interactive job application form", "resource": "https://developer.mozilla.org/en-US/docs/Web/JavaScript/Guide"},
    "html": {"level": "Beginner", "category": "Frontend", "topics": ["Semantic HTML", "Forms and inputs", "Tables and accessibility", "Page structure"], "project": "Create a responsive candidate profile page", "resource": "https://developer.mozilla.org/en-US/docs/Learn/HTML"},
    "css": {"level": "Beginner", "category": "Frontend", "topics": ["Selectors and box model", "Flexbox and Grid", "Responsive design", "Accessibility and states"], "project": "Style a responsive recruitment dashboard", "resource": "https://developer.mozilla.org/en-US/docs/Learn/CSS"},
    "django": {"level": "Beginner", "category": "Backend development", "topics": ["Projects, apps and URL routing", "Views, templates and models", "Forms and database migrations", "Authentication and deployment basics"], "project": "Build a small Django task manager with create, edit and delete features", "resource": "https://docs.djangoproject.com/en/stable/intro/tutorial01/"},
    "numpy": {"level": "Beginner", "category": "Python data tools", "topics": ["Create and inspect arrays", "Indexing, slicing and reshaping", "Vectorized operations and broadcasting", "Basic statistics and linear algebra"], "project": "Analyze a small dataset using NumPy arrays", "resource": "https://numpy.org/learn/"},
    "pandas": {"level": "Beginner", "category": "Python data tools", "topics": ["Series and DataFrames", "Read and write CSV files", "Filter, sort and clean data", "Group, merge and summarize datasets"], "project": "Create a CSV analysis report using Pandas", "resource": "https://pandas.pydata.org/docs/getting_started/"},
    "testing": {"level": "Beginner", "category": "Software quality", "topics": ["Test cases and assertions", "Unit tests and fixtures", "Testing Flask routes", "Test coverage and debugging failures"], "project": "Write pytest tests for a small Flask application", "resource": "https://docs.pytest.org/en/stable/getting-started.html"},
}
DEFAULT_SKILL_GUIDE = {"level": "Beginner", "category": "Technical skill", "topics": ["Understand the fundamentals", "Learn common terminology and workflows", "Complete guided exercises", "Build and review a small practical example"], "project": "Create a small practical project demonstrating this skill", "resource": "https://www.google.com/search?q=free+official+tutorial+"}


# ===================== HTML LAYOUT / CSS =====================
BASE_HTML = """
<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{{ title }} | TalentLens AI</title>
<style>
*{box-sizing:border-box}body{margin:0;font-family:Arial,sans-serif;background:#f4f6fb;color:#20263a}
nav{background:#202b50;padding:16px 5%;display:flex;flex-wrap:wrap;gap:18px}nav a{color:white;text-decoration:none;font-weight:bold}
main{max-width:1100px;margin:30px auto;padding:0 18px}h1{margin-top:0}.card{background:white;border-radius:12px;padding:22px;margin-bottom:18px;box-shadow:0 3px 14px #15244b10;overflow-wrap:anywhere}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:15px}.metric{font-size:28px;font-weight:bold;margin-top:8px}
form label{
    display:block;
    margin:22px 0 9px;
    font-weight:bold;
    color:#202b50;
}
form input[type=text],
form textarea,
form input[type=file]{
    display:block;
    width:100%;
    padding:13px;
    margin-bottom:8px;
    border:1px solid #ccd2e0;
    border-radius:8px;
    background:#fff;
    font-size:15px;
}
form textarea{
    min-height:160px;
    resize:vertical;
    line-height:1.5;
}
form input:focus,
form textarea:focus{
    outline:none;
    border-color:#4358d8;
    box-shadow:0 0 0 3px #4358d820;
}input[type=text],textarea,input[type=file]{width:100%;padding:12px;border:1px solid #ccd2e0;border-radius:7px}textarea{min-height:140px;resize:vertical}
button,.button{display:inline-block;background:#4358d8;color:white;padding:11px 16px;border:0;border-radius:7px;text-decoration:none;cursor:pointer;margin-top:12px}button:hover,.button:hover{background:#3045bf}
table{width:100%;border-collapse:collapse;background:white}th,td{padding:12px;border-bottom:1px solid #e8eaf1;text-align:left}th{background:#eef1fa}.table-wrap{overflow-x:auto}.pill{display:inline-block;padding:5px 9px;margin:3px;border-radius:20px;background:#e8edff;font-size:13px}.muted{color:#657087}.flash{background:#fff1d6;padding:12px;border-radius:7px;margin-bottom:12px}footer{text-align:center;padding:25px;color:#657087}
.gap-level{display:inline-block;background:#eef1fa;padding:5px 9px;border-radius:20px;font-size:12px}.gap-item{border:1px solid #e6e9f2;border-radius:9px;padding:15px;margin:12px 0}.gap-item h3{margin:0 0 8px;text-transform:capitalize}.roadmap-week{border-left:3px solid #4358d8;padding:8px 14px;margin:10px 0;background:#f8f9fd}.resource-link{color:#354bc4;font-weight:bold}

.dashboard-stats {
    display: grid;
    grid-template-columns: repeat(4, minmax(0, 1fr));
    gap: 18px;
    margin-bottom: 24px;
}

.dashboard-stat {
    background: white;
    border-radius: 14px;
    padding: 22px;
    box-shadow: 0 3px 14px #15244b10;
    border: 1px solid #e9ecf4;
    color: #657087;
    font-size: 14px;
}

.dashboard-stat .metric {
    color: #202b50;
    font-size: 30px;
    font-weight: 700;
    margin-top: 12px;
}

.dashboard-table {
    width: 100%;
    background: white;
    border-radius: 14px;
    padding: 24px;
    box-shadow: 0 3px 14px #15244b10;
    overflow-x: auto;
}

.dashboard-table h2 {
    margin-top: 0;
    color: #202b50;
}

.dashboard-table table {
    min-width: 600px;
}

.dashboard-table th {
    color: #202b50;
    font-size: 14px;
    padding: 15px;
}

.dashboard-table td {
    padding: 15px;
    font-size: 14px;
}

.dashboard-table tr:hover {
    background: #f7f8fc;
}

.match-score {
    color: #3045bf;
    font-weight: 700;
    white-space: nowrap;
}

@media(max-width:800px) {
    .dashboard-stats {
        grid-template-columns: repeat(2, minmax(0, 1fr));
    }
}

@media(max-width:600px) {
    main { margin-top: 20px; }
    .card { padding: 16px; }
    th, td { padding: 9px; }
    .dashboard-stats {
        grid-template-columns: 1fr 1fr;
        gap: 10px;
    }
    .dashboard-stat {
        padding: 15px;
    }
    .dashboard-table {
        padding: 15px;
    }
}

</style></head><body><nav>
<a href="{{ url_for('index') }}">Home</a><a href="{{ url_for('dashboard') }}">Dashboard</a>
<a href="{{ url_for('history') }}">History</a><a href="{{ url_for('download_report') }}">Download CSV</a>
<a href="{{ url_for('compare_candidates') }}">Candidate Comparison</a>
<a href="{{ url_for('learning_analytics') }}">Learning Analytics</a>
<a href="{{ url_for('health_check') }}">System Health</a></nav><main>
{% with messages = get_flashed_messages() %}{% for message in messages %}<div class="flash">{{ message }}</div>{% endfor %}{% endwith %}
{{ content|safe }}</main><footer>AI-Powered Resume Screening and Candidate Ranking System</footer></body></html>
"""
def page(title, content, **context):
    body = render_template_string(content, **context)
    return render_template_string(BASE_HTML, title=title, content=body)
# ===================== HOME =====================
HOME_HTML = """
<h1>TalentLens AI</h1><p class="muted">Upload multiple resumes and compare them against a job description.</p>
<div class="card"><form action="{{ url_for('screen') }}" method="post" enctype="multipart/form-data"><input type="hidden" name="csrf_token" value="{{ csrf_token() }}"><label for="job_title">Job title</label><input id="job_title" name="job_title" type="text" maxlength="255" placeholder="Example: Python Developer" required>
<label for="job_description">Job description and required skills</label><textarea id="job_description" name="job_description" required minlength="10" placeholder="Enter responsibilities, qualifications and required skills. Example: Python, Flask, MySQL, NLP, machine learning, communication."></textarea>
<label for="resumes">Upload resumes (PDF, DOCX or TXT)</label><input id="resumes" name="resumes" type="file" accept=".pdf,.docx,.txt" multiple required>
<p class="muted">Maximum 5 MB per resume. Maximum total upload size: 50 MB.</p><button type="submit">Screen Resumes</button></form></div>
<div class="card"><h2>How it works</h2><ol><li>Upload one or more resumes.</li><li>Enter the job description.</li><li>The system extracts resume text.</li><li>It compares text similarity and recognized skills.</li><li>Results are saved for dashboard and history.</li></ol><p class="muted">Scores are screening estimates, not hiring decisions. Review candidates fairly and manually.</p></div>
"""
@app.route("/")
def index():
    return page("Home", HOME_HTML)
# ===================== SCREEN RESUMES =====================
@app.route("/screen", methods=["POST"])
def screen():
    job_title = request.form.get("job_title", "").strip()
    job_description = request.form.get("job_description", "").strip()
    files = [f for f in request.files.getlist("resumes") if f and f.filename and f.filename.strip()]
    if not job_title:
        flash("Please enter a job title.")
        return redirect(url_for("index"))
    if len(job_title) > 255:
        flash("The job title must be 255 characters or fewer.")
        return redirect(url_for("index"))
    if len(job_description) < 10:
        flash("Please enter a meaningful job description of at least 10 characters.")
        return redirect(url_for("index"))
    if not files:
        flash("Please select at least one resume.")
        return redirect(url_for("index"))
    results = []
    for uploaded_file in files:
        filename = secure_filename(uploaded_file.filename)
        if not filename or not allowed_file(filename):
            results.append({"candidate_name": filename or "Unknown file", "filename": filename or "Unknown file", "error": "Unsupported file type. Upload PDF, DOCX or TXT."})
            continue
        try:
            uploaded_file.stream.seek(0)
            file_bytes = uploaded_file.read()
            uploaded_file.stream.seek(0)

            if not file_bytes:
                raise ValueError("The uploaded resume is empty.")

            if len(file_bytes) > MAX_RESUME_SIZE:
                raise ValueError("Resume is too large. Maximum size per resume is 5 MB.")

            resume_hash = hashlib.sha256(file_bytes).hexdigest()
            if is_duplicate_resume(resume_hash, job_title):
                results.append({
                    "candidate_name": filename,
                    "filename": filename,
                    "error": "This resume has already been screened for this job title."
                })
                continue

        except mysql.connector.Error:
            app.logger.exception("Duplicate check failed for %s", filename)
            results.append({
                "candidate_name": filename,
                "filename": filename,
                "error": "Could not check for duplicates. Please try again."
            })
            continue

        try:
            resume_text = extract_resume_text(uploaded_file)

            if not resume_text.strip():
                raise ValueError(
                    "No readable text was found. Scanned PDFs may require OCR."
                )

            scores = calculate_match(resume_text, job_description)
            candidate_name = guess_candidate_name(filename, resume_text)
            matching, missing = scores["matching_skills"], scores["missing_skills"]

            required_count = len(matching) + len(missing)

            if required_count == 0:
                explanation = (
                    "No recognized skills were found in the job description. "
                    "Please add specific technical or professional skills "
                    "to calculate a reliable candidate match."
                )
            else:
                explanation = (
                    f"Found {len(matching)} required skills and "
                    f"{len(missing)} required skills not detected."
                )

            candidate = {
                "candidate_name": candidate_name,
                "filename": filename,
                "job_title": job_title,
                "resume_hash": resume_hash,
                **scores,
                "explanation": explanation
            }

            candidate["id"] = save_candidate(candidate)
            results.append(candidate)

        except ValueError as error:
            results.append({
                "candidate_name": filename,
                "filename": filename,
                "error": str(error)
            })

        except mysql.connector.Error:
            app.logger.exception(
                "Database error while processing %s", filename
            )
            results.append({
                "candidate_name": filename,
                "filename": filename,
                "error": "A database error occurred while saving this candidate."
            })

        except Exception:
            app.logger.exception("Could not process %s", filename)
            results.append({
                "candidate_name": filename,
                "filename": filename,
                "error": "Could not process this file. Check that it is a valid, readable resume."
            })

    valid_results = sorted([r for r in results if "match_score" in r], key=lambda r: r["match_score"], reverse=True)
    errors = [r for r in results if "error" in r]
    average = round(sum(r["match_score"] for r in valid_results) / len(valid_results), 2) if valid_results else 0
    content = """
    <h1>Screening Results</h1><div class="grid">
    <div class="card">Processed successfully<div class="metric">{{ count }}</div></div>
    <div class="card">Average match score<div class="metric">{{ average }}%</div></div>
   <div class="card">Strong matches (75%+)<div class="metric">{{ strong }}</div></div>
    <div class="card">Files needing attention<div class="metric">{{ error_count }}</div></div></div>
    <div class="card table-wrap"><h2>Ranked candidates</h2><table><thead><tr><th>Rank</th><th>Candidate</th><th>Match</th><th>Text similarity</th><th>Skill score</th><th>Details</th></tr></thead><tbody>
    {% for c in results %}<tr><td>{{ loop.index }}</td><td>{{ c.candidate_name }}</td><td><strong>{{ c.match_score }}%</strong></td><td>{{ c.similarity_score }}%</td><td>{{ c.skill_score }}%</td><td><a href="{{ url_for('candidate_details', candidate_id=c.id) }}">View</a></td></tr>
    {% else %}<tr><td colspan="6">No candidates were successfully screened.</td></tr>{% endfor %}</tbody></table></div>
    {% if errors %}<div class="card"><h2>Files not processed</h2><ul>{% for item in errors %}<li><strong>{{ item.filename }}:</strong> {{ item.error }}</li>{% endfor %}</ul></div>{% endif %}
    <a class="button" href="{{ url_for('index') }}">Screen More Resumes</a> <a class="button" href="{{ url_for('dashboard') }}">Open Dashboard</a>
    """
    return page("Screening Results", content, results=valid_results, errors=errors, count=len(valid_results), average=average,
              strong=sum(r["match_score"] >= 75 for r in valid_results), error_count=len(errors))
# ===================== DASHBOARD =====================
@app.route("/dashboard")
def dashboard():
    try:
      candidates = sorted(
    get_candidates(),
    key=lambda c: (
        float(c.get("match_score") or 0),
        int(c.get("id") or 0)
    ),
    reverse=True
)
    except mysql.connector.Error:
        app.logger.exception("Dashboard database error")
        return "Database connection failed. Check your .env settings and visit /test-db.", 500
    total = len(candidates)
    average = round(sum(c["match_score"] for c in candidates) / total, 2) if total else 0

    content = """
    <h1>Recruitment Dashboard</h1>
    <p class="muted">Overview of screened candidates and their job matching performance.</p>

    <div class="dashboard-stats">
        <div class="dashboard-stat">
            Total Screened
            <div class="metric">{{ total }}</div>
        </div>

        <div class="dashboard-stat">
            Average Match
            <div class="metric">{{ average }}%</div>
        </div>

        <div class="dashboard-stat">
            Strong Matches
            <div class="metric">{{ strong }}</div>
            <small>75% and above</small>
        </div>

        <div class="dashboard-stat">
            Low Matches
            <div class="metric">{{ low }}</div>
            <small>Below 50%</small>
        </div>
    </div>

    <section class="dashboard-table">
        <h2>Top 10 Candidates</h2>
        <p class="muted">Candidates ranked by their overall job match score.</p>

        <table>
            <thead>
                <tr>
                    <th>Rank</th>
                    <th>Candidate Name</th>
                    <th>Job Position</th>
                    <th>Match Score</th>
                    <th>Details</th>
                </tr>
            </thead>

            <tbody>
                {% for c in candidates[:10] %}
                <tr>
                    <td>{{ loop.index }}</td>
                    <td><strong>{{ c.candidate_name }}</strong></td>
                    <td>{{ c.job_title }}</td>
                    <td>
                        <span class="match-score">{{ c.match_score }}%</span>
                    </td>
                    <td>
                        <a href="{{ url_for('candidate_details', candidate_id=c.id) }}">View Profile</a>
                    </td>
                </tr>
                {% else %}
                <tr>
                    <td colspan="5">No candidates have been screened yet.</td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
    </section>
    """

    return page("Dashboard", content, candidates=candidates, total=total, average=average,
               strong=sum(c["match_score"] >= 75 for c in candidates), low=sum(c["match_score"] < 50 for c in candidates))
# ===================== HISTORY =====================
@app.route("/history")
def history():
    try:
        candidates = get_candidates()
    except mysql.connector.Error:
        app.logger.exception("History database error")
        return "Database connection failed. Check /test-db.", 500
    content = """
    <h1>Screening History</h1><div class="card table-wrap"><table><thead><tr><th>Date</th><th>Candidate</th><th>Resume</th><th>Job title</th><th>Match</th><th>Details</th></tr></thead><tbody>
    {% for c in candidates %}<tr><td>{{ c.created_at }}</td><td>{{ c.candidate_name }}</td><td>{{ c.filename }}</td><td>{{ c.job_title }}</td><td>{{ c.match_score }}%</td><td><a href="{{ url_for('candidate_details', candidate_id=c.id) }}">View</a></td></tr>
    {% else %}<tr><td colspan="6">No saved screening history yet.</td></tr>{% endfor %}</tbody></table></div>
    """
    return page("History", content, candidates=candidates)
# ===================== SKILL GAP REPORT =====================

def build_skill_gap_report(missing_skills):

    report = []
    roadmap = []

    skill_guides = globals().get("SKILL_GAP_GUIDE", {})
    default_guide = globals().get("DEFAULT_SKILL_GUIDE", {
        "level": "Beginner",
        "category": "Technical Skill",
        "topics": [
            "Understand the fundamentals",
            "Learn important concepts",
            "Practice with coding exercises"
        ],
        "project": "Build a small practical project.",
        "resource": "#"
    })

    cleaned_skills = []

    for skill in (missing_skills or []):

        skill_name = str(skill).strip()

        if skill_name and skill_name.lower() not in [
            item.lower() for item in cleaned_skills
        ]:
            cleaned_skills.append(skill_name)

    for index, skill in enumerate(cleaned_skills, start=1):

        guide = skill_guides.get(
            skill.lower(),
            default_guide
        )

        item = {
            "skill": skill,
            "level": guide.get("level", "Beginner"),
            "category": guide.get("category", "Technical Skill"),
            "topics": guide.get("topics", []),
            "project": guide.get(
                "project",
                "Build a practical project using this skill."
            ),
            "resource": guide.get("resource", "#")
        }

        report.append(item)

        roadmap.append({
            "week": index,
            "skill": skill,
            "focus": item["topics"]
        })

    return {
        "items": report,
        "roadmap": roadmap
    }
# ===================== CANDIDATE DETAILS =====================
def get_match_status(score):
    """Convert numeric screening score into a readable status."""

    score = float(score or 0)

    if score >= 75:
        return "Strong Match", "strong"

    elif score >= 50:
        return "Moderate Match", "moderate"

    else:
        return "Low Match", "low"
# ===================== RECOMMENDED SKILLS =====================

def get_recommended_skills(job_title, existing_skills=None):
    """Recommend optional skills while excluding skills already detected."""

    existing_keys = set(
        canonicalize_skill_list(existing_skills or [])
    )

    # Treat Git and GitHub as already covered if either is detected.
    if "git" in existing_keys or "github" in existing_keys:
        existing_keys.add("git and github")

    job = str(job_title or "").strip().lower()

    recommendations = {
        "python developer": [
            "advanced python",
            "data structures and algorithms",
            "flask",
            "rest api",
            "unit testing",
            "git and github"
        ],

        "frontend developer": [
            "javascript",
            "react",
            "typescript",
            "responsive web design",
            "frontend testing",
            "web accessibility"
        ],

        "ai and machine learning": [
            "deep learning",
            "pandas",
            "numpy",
            "model deployment",
            "neural networks",
            "large language models"
        ]
    }

    selected = recommendations.get(job, [
        "problem solving",
        "software testing",
        "git and github",
        "communication skills"
    ])

    filtered = []

    for skill in selected:
        skill_key = canonicalize_skill_name(skill)

        if skill_key not in existing_keys:
            filtered.append({
                "skill": skill,
                "reason": "Additional skill recommended for professional development."
            })

    return filtered


# ===================== CANDIDATE PROFILE =====================

@app.route("/candidate/<int:candidate_id>")
def candidate_details(candidate_id):
    """Display the complete recruiter-facing candidate profile."""

    # Get candidate from database
    try:
        candidate = get_candidate(candidate_id)

        if not candidate:
            return "Candidate not found.", 404

        all_candidates = get_candidates()

    except mysql.connector.Error:
        app.logger.exception("Could not load candidate profile")
        return "Database connection failed. Please check MySQL.", 500

    # Candidate scores
    match_score = float(candidate.get("match_score") or 0)
    similarity_score = float(candidate.get("similarity_score") or 0)
    skill_score = float(candidate.get("skill_score") or 0)

    status, status_class = get_match_status(match_score)

    # Calculate candidate ranking
    ranked_candidates = sorted(
        all_candidates,
        key=lambda item: float(item.get("match_score") or 0),
        reverse=True
    )

    candidate_rank = next(
        (
            index
            for index, item in enumerate(ranked_candidates, start=1)
            if int(item.get("id") or 0) == candidate_id
        ),
        None
    )

    total_candidates = len(ranked_candidates)

    # Matching and missing skills
    matching_skills = candidate.get("matching_skills") or []
    missing_skills = candidate.get("missing_skills") or []

    if isinstance(matching_skills, str):
        matching_skills = json.loads(matching_skills)

    if isinstance(missing_skills, str):
        missing_skills = json.loads(missing_skills)

    # Resume evidence
    evidence = candidate.get("skill_evidence") or {}

    if isinstance(evidence, str):
        try:
            evidence = json.loads(evidence)
        except (TypeError, json.JSONDecodeError):
            evidence = {}

    if not isinstance(evidence, dict):
        evidence = {}

    # AI skill-gap analysis
    gap = build_skill_gap_report(missing_skills)
    gap_items = gap.get("items", [])

    # Additional skill recommendations
    recommended_skills = get_recommended_skills(
        candidate.get("job_title"),
        matching_skills + missing_skills
    )

    # Build a simple two-week learning roadmap
    learning_roadmap = []

    for index, item in enumerate(gap_items):
        skill = item.get("skill", "Additional skill")

        week = 1 if index < (len(gap_items) + 1) // 2 else 2

        learning_roadmap.append({
            "week": week,
            "skill": skill,
            "task": (
                f"Learn the fundamentals of {skill} and practise with "
                "small exercises."
                if week == 1
                else f"Practise {skill} through a small practical project."
            )
        })

    # Scoring explanation
    scoring_explanation = (
        f"Overall Match Score = (Text Similarity × 40%) + "
        f"(Skill Score × 60%). "
        f"({similarity_score:.2f} × 0.40) + "
        f"({skill_score:.2f} × 0.60) = {match_score:.2f}%."
    )

    # Recruiter summary
    if match_score >= 75:
        recruiter_summary = (
            "This candidate has a strong overall match with the job "
            "requirements. Consider shortlisting for the next stage."
        )
    elif match_score >= 50:
        recruiter_summary = (
            "This candidate has a moderate match. Review the missing "
            "skills and supporting resume evidence before shortlisting."
        )
    else:
        recruiter_summary = (
            "This candidate currently has a low overall match. "
            "Review the skill gaps and resume evidence carefully."
        )

    # Candidate profile HTML
    content = """
    <h1>Candidate Profile</h1>

    <div class="card">
        <h2>{{ c.get('candidate_name', 'Unknown Candidate') }}</h2>
        <p class="muted">{{ c.get('job_title', 'Job title not available') }}</p>
        <p><strong>Resume:</strong> {{ c.get('filename', 'Not available') }}</p>

        <span class="badge {{ status_class }}">{{ status }}</span>

        <p><strong>Candidate Ranking:</strong>
        #{{ rank if rank else 'N/A' }} out of {{ total }}</p>
    </div>

    <div class="card">
        <h2>Screening Scores</h2>

        <div class="grid">
            <div>
                <h3>{{ "%.2f"|format(match_score) }}%</h3>
                <p class="muted">Overall Match</p>
            </div>

            <div>
                <h3>{{ "%.2f"|format(similarity_score) }}%</h3>
                <p class="muted">Text Similarity</p>
            </div>

            <div>
                <h3>{{ "%.2f"|format(skill_score) }}%</h3>
                <p class="muted">Skill Score</p>
            </div>
        </div>

        <p><strong>Matching skills:</strong> {{ matching|length }}</p>
        <p><strong>Missing skills:</strong> {{ missing|length }}</p>
    </div>

    <div class="card">
        <h2>Recruiter Summary</h2>
        <p>{{ recruiter_summary }}</p>
    </div>

    <div class="card">
        <h2>Matching Skills</h2>

        {% for skill in matching %}
            <span class="badge strong">{{ skill }}</span>
        {% else %}
            <p>No matching skills were identified.</p>
        {% endfor %}
    </div>

    <div class="card">
        <h2>Missing Required Skills</h2>

        {% for skill in missing %}
            <span class="badge low">{{ skill }}</span>
        {% else %}
            <p>No missing required skills were identified.</p>
        {% endfor %}
    </div>

    <div class="card">
        <h2>Resume Evidence</h2>
        <p class="muted">
            These are sentences extracted from the uploaded resume
            that support detected skills.
        </p>

        {% for skill, snippets in evidence.items() %}
            <div style="padding:12px 0;border-bottom:1px solid #e8eaf1">
                <strong>{{ skill }}</strong>

                {% for snippet in snippets %}
                    <p>{{ snippet }}</p>
                {% endfor %}
            </div>
        {% else %}
            <p>No supporting resume sentences are available for this record.</p>
        {% endfor %}

        <p class="muted">
            Extracted evidence helps recruiters review the resume.
            It does not independently verify a candidate's proficiency.
        </p>
    </div>

    <div class="card">
        <h2>AI Skill Gap Analysis</h2>

        {% for item in gap_items %}
            <div style="padding:12px 0;border-bottom:1px solid #e8eaf1">
                <strong>{{ item.skill }}</strong>
                {% if item.get('description') %}
                    <p>{{ item.description }}</p>
                {% endif %}
            </div>
        {% else %}
            <p>No skill gaps were identified for this candidate.</p>
        {% endfor %}
    </div>

    <div class="card">
        <h2>Two-Week Learning Roadmap</h2>

        {% for item in roadmap %}
            <div style="padding:12px 0;border-bottom:1px solid #e8eaf1">
                <strong>Week {{ item.week }}: {{ item.skill }}</strong>
                <p>{{ item.task }}</p>
            </div>
        {% else %}
            <p>No additional learning roadmap is required.</p>
        {% endfor %}
    </div>

    <div class="card">
        <h2>Additional Recommended Skills</h2>

        {% for item in recommended %}
            <div style="padding:10px 0;border-bottom:1px solid #e8eaf1">
                <strong>{{ item.skill }}</strong>
                <p class="muted">{{ item.reason }}</p>
            </div>
        {% else %}
            <p>No additional recommendations at this time.</p>
        {% endfor %}
    </div>

    <div class="card">
        <h2>How the Match Score Is Calculated</h2>
        <p>{{ scoring_explanation }}</p>
    </div>

    <div class="card">
        <h2>Candidate Actions</h2>
        <p>
            <a class="button"
               href="{{ url_for('recruiter_progress', candidate_id=c.id) }}">
               View Skill Progress
            </a>
        </p>
        <p>
            <a class="button" href="{{ url_for('compare_candidates') }}">
                Compare Candidates
            </a>
        </p>
        <p><a href="{{ url_for('history') }}">Back to Screening History</a></p>
    </div>
    """

    return page(
        "Candidate Profile",
        content,
        c=candidate,
        status=status,
        status_class=status_class,
        rank=candidate_rank,
        total=total_candidates,
        match_score=match_score,
        similarity_score=similarity_score,
        skill_score=skill_score,
        matching=matching_skills,
        missing=missing_skills,
        evidence=evidence,
        gap_items=gap_items,
        roadmap=learning_roadmap,
        recommended=recommended_skills,
        recruiter_summary=recruiter_summary,
        scoring_explanation=scoring_explanation
    )

# ===================== END CANDIDATE PROFILE =====================

# ===================== CANDIDATE SKILL PROGRESS TRACKER =====================

PROGRESS_STATUSES = ("Not Started", "Learning", "Completed")


def ensure_candidate_progress(candidate_id, skills):
    """Create portal access and initialize missing skill records."""

    connection = cursor = None

    try:
        connection = get_db_connection()
        cursor = connection.cursor()

        cursor.execute(
            """
            SELECT access_token
            FROM candidate_progress_access
            WHERE candidate_id = %s
            """,
            (candidate_id,)
        )

        row = cursor.fetchone()

        if row:
            token = row[0]
        else:
            token = secrets.token_urlsafe(32)

            cursor.execute(
                """
                INSERT INTO candidate_progress_access
                (candidate_id, access_token)
                VALUES (%s, %s)
                """,
                (candidate_id, token)
            )

        cleaned_skills = canonicalize_skill_list(skills or [])

        for skill_name in cleaned_skills:
            cursor.execute(
                """
                INSERT IGNORE INTO candidate_skill_progress
                (candidate_id, skill, status)
                VALUES (%s, %s, 'Not Started')
                """,
                (candidate_id, skill_name)
            )

        connection.commit()
        return token

    except Exception:
        if connection is not None:
            connection.rollback()
        raise

    finally:
        if cursor is not None:
            cursor.close()

        if connection is not None and connection.is_connected():
            connection.close()


def initialize_all_candidate_progress():
    """Initialize progress tracking for existing candidates."""

    candidates = get_candidates()
    initialized_count = 0

    for candidate in candidates:
        candidate_id = candidate["id"]
        missing_skills = candidate.get("missing_skills", [])

        gap = build_skill_gap_report(missing_skills)

        skills_to_track = [
            item["skill"] for item in gap["items"]
        ]

        ensure_candidate_progress(candidate_id, skills_to_track)
        initialized_count += 1

    return initialized_count


def fetch_candidate_progress(candidate_id):
    """Fetch the learning progress of one candidate."""

    connection = cursor = None

    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)

        cursor.execute(
            """
            SELECT id, skill, status, updated_at
            FROM candidate_skill_progress
            WHERE candidate_id = %s
            ORDER BY skill
            """,
            (candidate_id,)
        )

        return cursor.fetchall()

    finally:
        if cursor is not None:
            cursor.close()

        if connection is not None and connection.is_connected():
            connection.close()


def progress_summary(rows):
    """Calculate candidate learning progress."""

    total = len(rows)

    completed = sum(
        1 for row in rows
        if row["status"] == "Completed"
    )

    learning = sum(
        1 for row in rows
        if row["status"] == "Learning"
    )

    percent = round((completed / total) * 100, 1) if total else 0

    return {
        "total": total,
        "completed": completed,
        "learning": learning,
        "not_started": total - completed - learning,
        "percent": percent
    }


@app.route("/candidate/<int:candidate_id>/progress")
def recruiter_progress(candidate_id):
    """Recruiter view of candidate learning progress."""

    candidate = get_candidate(candidate_id)

    if not candidate:
        return "Candidate not found.", 404

    gap = build_skill_gap_report(
        candidate.get("missing_skills", [])
    )

    try:
        token = ensure_candidate_progress(
            candidate_id,
            [item["skill"] for item in gap["items"]]
        )

        rows = fetch_candidate_progress(candidate_id)

    except mysql.connector.Error:
        app.logger.exception("Could not load candidate skill progress")
        return "Could not load skill progress. Check MySQL.", 500

    summary = progress_summary(rows)

    portal_url = url_for(
        "candidate_progress_portal",
        token=token,
        _external=True
    )

    content = """
    <h1>Candidate Skill Progress</h1>

    <div class="card">
        <h2>{{ c.candidate_name }}</h2>
        <p class="muted">{{ c.job_title }}</p>

        <p><strong>{{ summary.percent }}%</strong>
        of listed skill gaps completed</p>

        <div style="height:12px;background:#e8eaf1;border-radius:20px;overflow:hidden">
            <div style="height:12px;width:{{ summary.percent }}%;background:#16804a"></div>
        </div>

        <p>
            {{ summary.completed }} completed ·
            {{ summary.learning }} learning ·
            {{ summary.not_started }} not started
        </p>
    </div>

    <div class="card">
        <h2>Candidate Update Link</h2>

        <p>
            Share this private link with the candidate so they can
            update their learning status.
        </p>

        <input type="text" readonly
               value="{{ portal_url }}"
               onclick="this.select()"
               style="width:100%;padding:11px;border:1px solid #ccd2e0;border-radius:7px">

        <p>
            <a class="button" href="{{ portal_url }}"
               target="_blank" rel="noopener">
               Open Candidate Portal
            </a>
        </p>
    </div>

    <div class="card table-wrap">
        <h2>Skill Status</h2>

        <table>
            <thead>
                <tr>
                    <th>Skill</th>
                    <th>Status</th>
                    <th>Last Updated</th>
                </tr>
            </thead>

            <tbody>
                {% for row in rows %}
                <tr>
                    <td>{{ row.skill }}</td>
                    <td>{{ row.status }}</td>
                    <td>{{ row.updated_at }}</td>
                </tr>
                {% else %}
                <tr>
                    <td colspan="3">No missing skills were listed.</td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
    </div>

    <a class="button"
       href="{{ url_for('candidate_details', candidate_id=c.id) }}">
       Back to Candidate Profile
    </a>
    """

    return page(
        "Candidate Skill Progress",
        content,
        c=candidate,
        rows=rows,
        summary=summary,
        portal_url=portal_url
    )


@app.route("/candidate-progress/<token>", methods=["GET", "POST"])
def candidate_progress_portal(token):
    """Candidate-facing learning progress portal."""

    connection = cursor = None

    try:
        connection = get_db_connection()
        cursor = connection.cursor()

        cursor.execute(
            """
            SELECT candidate_id
            FROM candidate_progress_access
            WHERE access_token = %s
            """,
            (token,)
        )

        access = cursor.fetchone()

        if not access:
            return "This progress link is invalid or has expired.", 404

        candidate_id = int(access[0])

    except mysql.connector.Error:
        app.logger.exception("Candidate progress access lookup failed")
        return "Could not open the progress portal.", 500

    finally:
        if cursor is not None:
            cursor.close()

        if connection is not None and connection.is_connected():
            connection.close()

    candidate = get_candidate(candidate_id)

    if not candidate:
        return "Candidate record not found.", 404

    gap = build_skill_gap_report(
        candidate.get("missing_skills", [])
    )

    connection = cursor = None

    try:
        ensure_candidate_progress(
            candidate_id,
            [item["skill"] for item in gap["items"]]
        )

        rows = fetch_candidate_progress(candidate_id)

        if request.method == "POST":

            connection = get_db_connection()
            cursor = connection.cursor()

            for row in rows:
                new_status = request.form.get(
                    f"status_{row['id']}", ""
                ).strip()

                if new_status in PROGRESS_STATUSES:
                    cursor.execute(
                        """
                        UPDATE candidate_skill_progress
                        SET status = %s
                        WHERE id = %s AND candidate_id = %s
                        """,
                        (new_status, row["id"], candidate_id)
                    )

            connection.commit()

            flash("Your skill progress has been saved.")

            return redirect(
                url_for("candidate_progress_portal", token=token)
            )

    except mysql.connector.Error:
        app.logger.exception("Could not update candidate skill progress")
        return "Could not save progress. Please try again later.", 500

    finally:
        if cursor is not None:
            cursor.close()

        if connection is not None and connection.is_connected():
            connection.close()

    summary = progress_summary(rows)

    content = """
    <h1>My Skill Progress</h1>

    <div class="card">
        <h2>Welcome, {{ c.candidate_name }}</h2>
        <p class="muted">Learning plan for {{ c.job_title }}</p>

        <p><strong>{{ summary.percent }}%</strong> of listed skills completed</p>

        <div style="height:12px;background:#e8eaf1;border-radius:20px;overflow:hidden">
            <div style="height:12px;width:{{ summary.percent }}%;background:#16804a"></div>
        </div>

        <p>
            {{ summary.completed }} completed ·
            {{ summary.learning }} learning ·
            {{ summary.not_started }} not started
        </p>
    </div>

    <div class="card">
        <h2>Update Your Skills</h2>

        <p class="muted">
            Choose the status that best describes your learning.
            These updates are visible to the recruiter.
        </p>

        <form method="post">
            <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">

            {% for row in rows %}
            <div style="padding:13px 0;border-bottom:1px solid #e8eaf1">

                <label for="status_{{ row.id }}">{{ row.skill }}</label>

                <select id="status_{{ row.id }}"
                        name="status_{{ row.id }}"
                        style="padding:10px;border:1px solid #ccd2e0;border-radius:7px;min-width:190px">

                    {% for status in statuses %}
                    <option value="{{ status }}"
                        {% if row.status == status %}selected{% endif %}>
                        {{ status }}
                    </option>
                    {% endfor %}

                </select>
            </div>

            {% else %}
            <p>No skill gaps were listed. Great work!</p>
            {% endfor %}

            {% if rows %}
            <button type="submit">Save My Progress</button>
            {% endif %}
        </form>
    </div>

    <p class="muted">
        This tracker records self-reported learning progress.
        It does not independently verify skill proficiency.
    </p>
    """

    return page(
        "My Skill Progress",
        content,
        c=candidate,
        rows=rows,
        summary=summary,
        statuses=PROGRESS_STATUSES
    )


# ===================== END CANDIDATE SKILL PROGRESS TRACKER =====================


# ===================== DATABASE TEST =====================
@app.route("/test-db")
def test_db():
    connection = cursor = None
    try:
        connection = get_db_connection()
        cursor = connection.cursor()
        cursor.execute("SELECT DATABASE(), VERSION()")
        database_name, db_version = cursor.fetchone()
        cursor.execute("""SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = %s AND table_name = 'screening_results'""", (database_name,))
        table_exists = cursor.fetchone()[0] == 1
        cursor.execute("""SELECT COUNT(*) FROM information_schema.columns WHERE table_schema = %s AND table_name = 'screening_results' AND column_name = 'skill_evidence'""", (database_name,))
        evidence_column_exists = cursor.fetchone()[0] == 1
        return ("<h1>Database connection successful!</h1>"
                f"<p>Database: {escape(str(database_name))}</p>"
                f"<p>MySQL version: {escape(str(db_version))}</p>"
                f"<p>Screening table exists: {table_exists}</p>"
                f"<p>Skill evidence column exists: {evidence_column_exists}</p><p><a href='/'>Home</a></p>")
    except mysql.connector.Error:
        app.logger.exception("Database test failed")
        return "<h1>Database connection failed</h1><p>Check your local .env file and MySQL credentials.</p>", 500
    finally:
        if cursor is not None:
            cursor.close()
        if connection is not None and connection.is_connected():
            connection.close()
# ===================== HEALTH CHECK (FIXED) =====================
@app.route("/health")
def health_check():
    checks = {}
    packages = ["Flask", "mysql-connector-python", "scikit-learn", "PyMuPDF", "python-docx", "python-dotenv"]
    for package in packages:
        try:
            checks[package] = version(package)
        except PackageNotFoundError:
            checks[package] = "NOT INSTALLED"
    connection = cursor = None
    try:
        connection = get_db_connection()
        cursor = connection.cursor()
        cursor.execute("SELECT 1")
        cursor.fetchone()
        checks["MySQL database"] = "CONNECTED"
    except Exception:
        app.logger.exception("Health check database failure")
        checks["MySQL database"] = "CONNECTION FAILED"
    finally:
        if cursor is not None:
            cursor.close()
        if connection is not None and connection.is_connected():
            connection.close()
    all_ok = (
        checks.get("MySQL database") == "CONNECTED"
        and all(status != "NOT INSTALLED" for name, status in checks.items() if name != "MySQL database")
    )
    rows = "".join(f"<tr><td>{escape(str(name))}</td><td>{escape(str(status))}</td></tr>" for name, status in checks.items())
    status_text = "HEALTHY" if all_ok else "CHECK REQUIRED"
    status_color = "#16804a" if all_ok else "#b45309"
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>TalentLens AI Health Check</title>
    <style>body{{font-family:Arial,sans-serif;background:#f4f6fb;color:#20263a;margin:30px}}main{{max-width:850px;margin:auto;background:white;padding:24px;border-radius:12px}}table{{border-collapse:collapse;width:100%;margin-top:18px}}th,td{{border:1px solid #ddd;padding:12px;text-align:left}}th{{background:#eef1fa}}h2{{color:{status_color}}}a{{color:#4358d8}}</style></head><body><main>
    <h1>TalentLens AI — System Health</h1><h2>{status_text}</h2><p>This read-only check verifies Python packages and MySQL connectivity. It does not change screening records.</p>
    <table><thead><tr><th>Component</th><th>Status / Version</th></tr></thead><tbody>{rows}</tbody></table><p><a href="/dashboard">Back to Dashboard</a> | <a href="/">Home</a></p></main></body></html>""", (200 if all_ok else 503)
# ===================== CANDIDATE COMPARISON =====================

@app.route("/compare", methods=["GET", "POST"])
def compare_candidates():
    """Compare 2-5 candidates using a concise recruiter-friendly view."""

    try:
        all_candidates = get_candidates()
    except mysql.connector.Error:
        app.logger.exception("Candidate comparison database error")
        return "Database connection failed. Check /test-db.", 500

    # STEP 1: Candidate selection page
    if request.method == "GET":
        content = """
        <style>
            .compare-select label {
                display: flex;
                align-items: center;
                gap: 12px;
                padding: 12px;
                border-bottom: 1px solid #e8eaf1;
                cursor: pointer;
            }

            .compare-select label:hover {
                background: #f7f8fc;
            }

            .compare-select input {
                width: auto;
            }

            .compare-note {
                color: #657087;
                font-size: 13px;
            }
        </style>

        <h1>Candidate Comparison</h1>
        <p class="muted">
            Select 2 to 5 candidates applying for the same job.
        </p>

        <div class="card compare-select">
            <form method="post" action="{{ url_for('compare_candidates') }}">
            <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">

                {% for c in candidates %}
                    <label>
                        <input type="checkbox"
                               name="candidate_ids"
                               value="{{ c.id }}">

                        <span>
                            <strong>{{ c.candidate_name }}</strong><br>
                            <span class="compare-note">
                                {{ c.job_title }} ·
                                {{ '%.2f'|format(c.match_score or 0) }}% match
                            </span>
                        </span>
                    </label>
                {% else %}
                    <p>No saved candidates are available yet. Screen resumes first.</p>
                {% endfor %}

                <p class="compare-note">
                    Select between 2 and 5 candidates.
                </p>

                <button type="submit">Compare Candidates</button>
            </form>
        </div>
        """

        return page(
            "Candidate Comparison",
            content,
            candidates=all_candidates
        )

    # STEP 2: Validate selected candidates
    raw_ids = request.form.getlist("candidate_ids")

    try:
        selected_ids = list(
            dict.fromkeys(int(value) for value in raw_ids)
        )
    except (TypeError, ValueError):
        flash("Invalid candidate selection.")
        return redirect(url_for("compare_candidates"))

    if not 2 <= len(selected_ids) <= 5:
        flash("Please select between 2 and 5 candidates.")
        return redirect(url_for("compare_candidates"))

    selected = [
        c for c in all_candidates
        if int(c.get("id") or 0) in selected_ids
    ]

    if len(selected) != len(selected_ids):
        flash("One or more selected candidates could not be found.")
        return redirect(url_for("compare_candidates"))

    job_titles = {
        (c.get("job_title") or "").strip().casefold()
        for c in selected
    }

    if len(job_titles) != 1:
        flash("Please compare candidates screened for the same job title.")
        return redirect(url_for("compare_candidates"))

    # STEP 3: Rank candidates by their existing match score
    selected.sort(
        key=lambda c: float(c.get("match_score") or 0),
        reverse=True
    )

    # Calculate quick comparison highlights
    best_similarity = max(
        selected,
        key=lambda c: float(c.get("similarity_score") or 0)
    )

    most_skills = max(
        selected,
        key=lambda c: len(c.get("matching_skills") or [])
    )

    fewest_missing = min(
        selected,
        key=lambda c: len(c.get("missing_skills") or [])
    )

    content = """
    <style>
        .comparison-intro {
            color: #657087;
            margin-bottom: 20px;
        }

        .winner-card {
            background: #f0f7ff;
            border: 1px solid #b8d8ff;
            border-radius: 14px;
            padding: 22px;
            margin: 18px 0;
        }

        .winner-score {
            font-size: 38px;
            font-weight: 800;
            margin: 8px 0;
        }

        .winner-label {
            display: inline-block;
            background: #dbeafe;
            color: #1d4ed8;
            border-radius: 20px;
            padding: 5px 11px;
            font-size: 12px;
            font-weight: bold;
        }

        .quick-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
            gap: 12px;
            margin: 18px 0;
        }

        .quick-card {
            background: white;
            border: 1px solid #e5e7eb;
            border-radius: 11px;
            padding: 16px;
        }

        .quick-value {
            font-size: 19px;
            font-weight: bold;
            margin-top: 8px;
        }

        .comparison-table {
            width: 100%;
            border-collapse: collapse;
            min-width: 580px;
        }

        .comparison-table th,
        .comparison-table td {
            padding: 13px 12px;
            border-bottom: 1px solid #e8eaf1;
            text-align: left;
        }

        .comparison-table th {
            background: #f7f8fc;
        }

        .rank-first {
            color: #16804a;
            font-weight: bold;
        }

        .candidate-details {
            border: 1px solid #e5e7eb;
            border-radius: 10px;
            padding: 15px;
            margin: 12px 0;
            background: white;
        }

        .candidate-details summary {
            cursor: pointer;
            font-weight: bold;
        }

        .skill-tag {
            display: inline-block;
            background: #e8f5ed;
            color: #166534;
            padding: 5px 9px;
            border-radius: 15px;
            margin: 4px;
            font-size: 12px;
        }

        .missing-tag {
            display: inline-block;
            background: #fee2e2;
            color: #991b1b;
            padding: 5px 9px;
            border-radius: 15px;
            margin: 4px;
            font-size: 12px;
        }

        .comparison-actions {
            display: flex;
            flex-wrap: wrap;
            gap: 12px;
            align-items: center;
        }

        @media(max-width: 600px) {
            .winner-score {
                font-size: 30px;
            }
        }
    </style>

    <h1>Candidate Comparison</h1>

    <p class="comparison-intro">
        Job position: <strong>{{ selected[0].job_title }}</strong>
        · {{ selected|length }} candidates compared
    </p>

    <!-- TOP CANDIDATE -->
    <div class="winner-card">
        <span class="winner-label">TOP RANKED CANDIDATE</span>

        <h2>{{ selected[0].candidate_name }}</h2>

        <div class="winner-score">
            {{ '%.2f'|format(selected[0].match_score or 0) }}%
        </div>

        <p>Highest overall match score among selected candidates.</p>

        <a href="{{ url_for(
            'candidate_details',
            candidate_id=selected[0].id
        ) }}">
            View Candidate Profile →
        </a>
    </div>

    <!-- QUICK HIGHLIGHTS -->
    <h2>Quick Comparison</h2>

    <div class="quick-grid">

        <div class="quick-card">
            <div class="muted">Highest Text Similarity</div>
            <div class="quick-value">
                {{ best_similarity.candidate_name }}
            </div>
            <strong>
                {{ '%.2f'|format(best_similarity.similarity_score or 0) }}%
            </strong>
        </div>

        <div class="quick-card">
            <div class="muted">Most Matching Skills</div>
            <div class="quick-value">
                {{ most_skills.candidate_name }}
            </div>
            <strong>
                {{ most_skills.matching_skills|length }} skills
            </strong>
        </div>

        <div class="quick-card">
            <div class="muted">Fewest Missing Skills</div>
            <div class="quick-value">
                {{ fewest_missing.candidate_name }}
            </div>
            <strong>
                {{ fewest_missing.missing_skills|length }} not detected
            </strong>
        </div>

    </div>

    <!-- RANKING TABLE -->
    <div class="card">
        <h2>Candidate Ranking</h2>

        <div class="table-wrap">
            <table class="comparison-table">
                <thead>
                    <tr>
                        <th>Rank</th>
                        <th>Candidate</th>
                        <th>Overall Match</th>
                        <th>Text Similarity</th>
                        <th>Skill Score</th>
                        <th>Matching Skills</th>
                        <th>Missing Skills</th>
                        <th>Profile</th>
                    </tr>
                </thead>

                <tbody>
                    {% for c in selected %}
                    <tr>
                        <td>
                            {% if loop.first %}
                                <span class="rank-first">#1</span>
                            {% else %}
                                #{{ loop.index }}
                            {% endif %}
                        </td>

                        <td><strong>{{ c.candidate_name }}</strong></td>

                        <td>
                            <strong>
                                {{ '%.2f'|format(c.match_score or 0) }}%
                            </strong>
                        </td>

                        <td>
                            {{ '%.2f'|format(c.similarity_score or 0) }}%
                        </td>

                        <td>
                            {{ '%.2f'|format(c.skill_score or 0) }}%
                        </td>

                        <td>{{ c.matching_skills|length }}</td>

                        <td>{{ c.missing_skills|length }}</td>

                        <td>
                            <a href="{{ url_for(
                                'candidate_details',
                                candidate_id=c.id
                            ) }}">
                                View
                            </a>
                        </td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>
    </div>

    <!-- OPTIONAL DETAILS -->
    <div class="card">
        <h2>Detailed Candidate Information</h2>

        <p class="muted">
            Expand a candidate to see matching skills, missing skills,
            and available resume evidence.
        </p>

        {% for c in selected %}
        <details class="candidate-details">

            <summary>
                {{ c.candidate_name }} —
                {{ '%.2f'|format(c.match_score or 0) }}% match
            </summary>

            <h4>Matching Skills</h4>

            {% for skill in c.matching_skills %}
                <span class="skill-tag">✓ {{ skill }}</span>
            {% else %}
                <p class="muted">No matching skills detected.</p>
            {% endfor %}

            <h4>Missing Required Skills</h4>

            {% for skill in c.missing_skills %}
                <span class="missing-tag">{{ skill }}</span>
            {% else %}
                <p class="muted">No missing required skills detected.</p>
            {% endfor %}

            <h4>Resume Evidence</h4>

            {% if c.skill_evidence %}
                {% for skill, snippets in c.skill_evidence.items() %}
                    <p><strong>{{ skill }}</strong></p>
                    <ul>
                        {% for snippet in snippets %}
                            <li>{{ snippet }}</li>
                        {% endfor %}
                    </ul>
                {% endfor %}
            {% else %}
                <p class="muted">
                    No saved evidence snippets for this record.
                </p>
            {% endif %}

            <p class="muted">
                Missing evidence does not prove a candidate lacks a skill.
            </p>

            <a href="{{ url_for(
                'candidate_details',
                candidate_id=c.id
            ) }}">
                Open Full Candidate Profile →
            </a>

        </details>
        {% endfor %}
    </div>

    <!-- ACTIONS -->
    <div class="card">
        <h2>Export Comparison</h2>

        <p class="muted">
            Download the detailed comparison as a CSV spreadsheet.
        </p>
        <div class="comparison-actions">
        <form method="post" action="{{ url_for('compare_export') }}">
        <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">

        {% for c in selected %}
            <input type="hidden"
                   name="candidate_ids"
                   value="{{ c.id }}">
        {% endfor %}

        <button type="submit">Download Comparison CSV</button>
    </form>

    <a class="button"
       href="{{ url_for('compare_candidates') }}">
        Compare Other Candidates
        </a>
    </div>
    </div>
    """

    return page(
        "Candidate Comparison",
        content,
        selected=selected,
        best_similarity=best_similarity,
        most_skills=most_skills,
        fewest_missing=fewest_missing
    )


# ===================== LEARNING ANALYTICS =====================
def collect_learning_analytics(job_title_filter=None):
    """Build recruiter analytics from saved screening and progress rows.

    This function is read-only: it does not seed, reset, or modify progress.
    """
    connection = cursor = None
    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        query = """
            SELECT s.id, s.candidate_name, s.job_title,
                   p.skill, p.status, p.updated_at
            FROM screening_results AS s
            LEFT JOIN candidate_skill_progress AS p
                   ON p.candidate_id = s.id
        """
        params = ()
        if job_title_filter:
            query += " WHERE LOWER(TRIM(s.job_title)) = LOWER(TRIM(%s))"
            params = (job_title_filter,)
        query += " ORDER BY s.job_title, s.candidate_name, p.skill"
        cursor.execute(query, params)
        records = cursor.fetchall()
    finally:
        if cursor is not None:
            cursor.close()
        if connection is not None and connection.is_connected():
            connection.close()

    grouped = {}
    for row in records:
        candidate_id = row['id']
        if candidate_id not in grouped:
            grouped[candidate_id] = {
                'id': candidate_id,
                'candidate_name': row['candidate_name'],
                'job_title': row['job_title'],
                'total': 0,
                'completed': 0,
                'learning': 0,
                'not_started': 0,
                'percent': 0.0,
            }
        item = grouped[candidate_id]
        if row['skill'] is not None:
            item['total'] += 1
            status = row['status'] or 'Not Started'
            if status == 'Completed':
                item['completed'] += 1
            elif status == 'Learning':
                item['learning'] += 1
            else:
                item['not_started'] += 1

    candidates = list(grouped.values())
    for item in candidates:
        item['percent'] = round(item['completed'] / item['total'] * 100, 1) if item['total'] else 0.0
    candidates.sort(key=lambda item: (-item['percent'], item['candidate_name'].casefold()))

    total_skills = sum(item['total'] for item in candidates)
    completed = sum(item['completed'] for item in candidates)
    learning = sum(item['learning'] for item in candidates)
    not_started = sum(item['not_started'] for item in candidates)
    tracked_candidates = sum(1 for item in candidates if item['total'] > 0)
    overall_percent = round(completed / total_skills * 100, 1) if total_skills else 0.0

    return {
        'candidates': candidates,
        'candidate_count': len(candidates),
        'tracked_candidates': tracked_candidates,
        'total_skills': total_skills,
        'completed': completed,
        'learning': learning,
        'not_started': not_started,
        'overall_percent': overall_percent,
        'job_titles': sorted({item['job_title'] for item in candidates if item['job_title']}),
    }


@app.route('/learning-analytics')
def learning_analytics():
    job_title_filter = request.args.get('job_title', '').strip()
    try:
        analytics = collect_learning_analytics(job_title_filter or None)
    except mysql.connector.Error:
        app.logger.exception('Learning analytics database error')
        return 'Could not load learning analytics. Check /test-db.', 500

    content = """
    <h1>Learning Analytics</h1>
    <p class="muted">Overview of candidate-reported progress for skills listed in their learning trackers.</p>
    <div class="grid">
      <div class="card">Candidates<div class="metric">{{ a.candidate_count }}</div></div>
      <div class="card">Candidates with tracked skills<div class="metric">{{ a.tracked_candidates }}</div></div>
      <div class="card">Overall completion<div class="metric">{{ a.overall_percent }}%</div></div>
      <div class="card">Skills tracked<div class="metric">{{ a.total_skills }}</div></div>
    </div>
    <div class="grid">
      <div class="card">Completed<div class="metric">{{ a.completed }}</div></div>
      <div class="card">Learning<div class="metric">{{ a.learning }}</div></div>
      <div class="card">Not started<div class="metric">{{ a.not_started }}</div></div>
    </div>
    <div class="card">
      <h2>Filter by job title</h2>
      <form method="get">
        <label for="job_title">Job title</label>
        <select id="job_title" name="job_title" style="width:100%;max-width:420px;padding:11px;border:1px solid #ccd2e0;border-radius:7px">
          <option value="">All job titles</option>
          {% for title in a.job_titles %}
            <option value="{{ title }}" {% if selected_job == title %}selected{% endif %}>{{ title }}</option>
          {% endfor %}
        </select>
        <button type="submit">Apply filter</button>
        <a class="button" href="{{ url_for('learning_analytics') }}">Clear</a>
      </form>
    </div>
    <div class="card table-wrap">
      <h2>Candidate learning progress</h2>
      <table><thead><tr><th>Candidate</th><th>Job title</th><th>Completed</th><th>Learning</th><th>Not started</th><th>Progress</th><th>Details</th></tr></thead><tbody>
      {% for c in a.candidates %}
        <tr>
          <td>{{ c.candidate_name }}</td><td>{{ c.job_title }}</td>
          <td>{{ c.completed }}</td><td>{{ c.learning }}</td><td>{{ c.not_started }}</td>
          <td>{{ c.percent }}%</td>
          <td><a href="{{ url_for('recruiter_progress', candidate_id=c.id) }}">View tracker</a></td>
        </tr>
      {% else %}
        <tr><td colspan="7">No candidate records found for this filter.</td></tr>
      {% endfor %}
      </tbody></table>
    </div>
    <p class="muted">Progress is self-reported and is not an independent assessment of skill proficiency. Candidates with no tracked skill gaps are included with 0 tracked skills.</p>
    <a class="button" href="{{ url_for('learning_analytics_export', job_title=selected_job) }}">Download Analytics CSV</a>
    """
    return page('Learning Analytics', content, a=analytics, selected_job=job_title_filter)


@app.route('/learning-analytics/export')
def learning_analytics_export():
    job_title_filter = request.args.get('job_title', '').strip()
    try:
        analytics = collect_learning_analytics(job_title_filter or None)
    except mysql.connector.Error:
        app.logger.exception('Learning analytics export database error')
        return 'Could not export learning analytics. Check /test-db.', 500

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Candidate ID', 'Candidate', 'Job title', 'Total tracked skills',
                     'Completed', 'Learning', 'Not started', 'Progress percent'])
    for item in analytics['candidates']:
        writer.writerow([
            item['id'],
            safe_csv_cell(item['candidate_name']),
            safe_csv_cell(item['job_title']),
            item['total'],
            item['completed'],
            item['learning'],
            item['not_started'],
            item['percent']
        ])
    response = make_response('\ufeff' + output.getvalue())
    response.headers['Content-Type'] = 'text/csv; charset=utf-8'
    response.headers['Content-Disposition'] = 'attachment; filename=talentlens_learning_analytics.csv'
    return response

# ===================== MAIN CSV REPORT DOWNLOAD =====================

@app.route("/download-report")
def download_report():
    try:
        candidates = get_candidates()
    except mysql.connector.Error:
        app.logger.exception("CSV report database error")
        return "Could not download the report. Check MySQL.", 500

    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow([
        "Candidate ID",
        "Candidate Name",
        "Job Title",
        "Overall Match Score",
        "Text Similarity Score",
        "Skill Score",
        "Matching Skills",
        "Missing Skills",
        "Created At"
    ])

    for candidate in candidates:
        writer.writerow([
            candidate.get("id", ""),
            safe_csv_cell(candidate.get("candidate_name", "")),
            safe_csv_cell(candidate.get("job_title", "")),
            candidate.get("match_score", 0),
            candidate.get("similarity_score", 0),
            candidate.get("skill_score", 0),
            safe_csv_cell(", ".join(candidate.get("matching_skills", []))),
            safe_csv_cell(", ".join(candidate.get("missing_skills", []))),
            safe_csv_cell(str(candidate.get("created_at", "")))
        ])

    response = make_response("\ufeff" + output.getvalue())
    response.headers["Content-Type"] = "text/csv; charset=utf-8"
    response.headers["Content-Disposition"] = (
        "attachment; filename=talentlens_candidate_report.csv"
    )

    return response


# ===================== END MAIN CSV REPORT DOWNLOAD =====================


# ===================== COMPARISON CSV EXPORT =====================
@app.route('/compare/export', methods=['POST'])
def compare_export():
    raw_ids = request.form.getlist('candidate_ids')
    try:
        selected_ids = list(dict.fromkeys(int(value) for value in raw_ids))
    except (TypeError, ValueError):
        flash('Invalid candidate selection for export.')
        return redirect(url_for('compare_candidates'))

    if not 2 <= len(selected_ids) <= 5:
        flash('Select between 2 and 5 candidates to export.')
        return redirect(url_for('compare_candidates'))

    try:
        all_candidates = get_candidates()
    except mysql.connector.Error:
        app.logger.exception('Comparison export database error')
        return 'Could not export comparison. Check /test-db.', 500

    selected = [c for c in all_candidates if int(c.get('id') or 0) in selected_ids]
    if len(selected) != len(selected_ids):
        flash('One or more selected candidates could not be found.')
        return redirect(url_for('compare_candidates'))
    if len({(c.get('job_title') or '').strip().casefold() for c in selected}) != 1:
        flash('Please compare candidates screened for the same job title.')
        return redirect(url_for('compare_candidates'))

    selected.sort(key=lambda c: float(c.get('match_score') or 0), reverse=True)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Rank', 'Candidate ID', 'Candidate', 'Job title', 'Overall match',
                     'Text similarity', 'Skill score', 'Matching skills', 'Missing skills',
                     'Resume evidence', 'Explanation', 'Created at'])
    for rank, c in enumerate(selected, start=1):
        writer.writerow([
            rank,
            c['id'],
            safe_csv_cell(c['candidate_name']),
            safe_csv_cell(c['job_title']),
            c['match_score'],
            c['similarity_score'],
            c['skill_score'],
            safe_csv_cell(', '.join(c['matching_skills'])),
            safe_csv_cell(', '.join(c['missing_skills'])),
            safe_csv_cell(json.dumps(c.get('skill_evidence', {}), ensure_ascii=False)),
            safe_csv_cell(c.get('explanation', '')),
            safe_csv_cell(c.get('created_at', ''))
        ])
    response = make_response('\ufeff' + output.getvalue())
    response.headers['Content-Type'] = 'text/csv; charset=utf-8'
    response.headers['Content-Disposition'] = 'attachment; filename=talentlens_candidate_comparison.csv'
    return response

if __name__ == "__main__":
    print("\n======================================")
    print("          TALENTLENS AI")
    print("======================================")

    print("\nChecking MySQL database...")
    initialize_database()
    print("Database initialized successfully.")

    print("\nInitializing candidate skill progress...")
    initialize_all_candidate_progress()
    print("Skill progress initialized for 26 candidates.")

    print("\nStarting Flask application...")
    print("Home: http://127.0.0.1:5001/")
    print("Dashboard: http://127.0.0.1:5001/dashboard")
    print("History: http://127.0.0.1:5001/history")
    print("Comparison: http://127.0.0.1:5001/compare")
    print("Learning Analytics: http://127.0.0.1:5001/learning-analytics")
    print("System Health: http://127.0.0.1:5001/health")
    print("Database Test: http://127.0.0.1:5001/test-db")

    print("\n======================================")
    print("       SERVER IS STARTING...")
    print("======================================")

    app.run(host="127.0.0.1", port=5001, debug=False, use_reloader=False)
