
import re


SKILLS = [
    "Python", "Java", "JavaScript", "TypeScript",
    "C++", "C", "HTML", "CSS", "SQL", "MySQL",
    "PostgreSQL", "MongoDB", "Flask", "Django",
    "React", "Node.js", "REST API", "Git", "GitHub",
    "Docker", "AWS", "Azure",
    "Machine Learning", "Deep Learning",
    "Natural Language Processing", "NLP",
    "NLTK", "spaCy", "Scikit-learn",
    "Pandas", "NumPy", "TensorFlow", "PyTorch",
    "TF-IDF", "Cosine Similarity",
    "Data Analysis", "Data Structures", "Algorithms",
    "Communication", "Problem Solving"
]


def normalize_text(text):
    if not isinstance(text, str):
        return ""

    text = text.lower()
    text = re.sub(r"[^a-z0-9+#.\- ]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def extract_skills(text):
    """Extract recognised skill names from resume or job-description text."""
    normalized = normalize_text(text)
    found = []

    for skill in SKILLS:
        skill_normalized = normalize_text(skill)

        if not skill_normalized:
            continue

        pattern = (
            r"(?<![a-z0-9])"
            + re.escape(skill_normalized)
            + r"(?![a-z0-9])"
        )

        if re.search(pattern, normalized):
            found.append(skill)

    return found


def calculate_skill_match(resume_skills, required_skills):
    """
    Compare two lists of skills.
    Also accepts strings and extracts skills from them.
    """

    if isinstance(resume_skills, str):
        resume_skills = extract_skills(resume_skills)
    elif not isinstance(resume_skills, (list, tuple, set)):
        resume_skills = []

    if isinstance(required_skills, str):
        required_skills = extract_skills(required_skills)
    elif not isinstance(required_skills, (list, tuple, set)):
        required_skills = []

    # Convert values to lists and compare case-insensitively.
    resume_lookup = {
        normalize_text(skill)
        for skill in resume_skills
        if isinstance(skill, str) and normalize_text(skill)
    }

    required = []
    seen = set()

    for skill in required_skills:
        if not isinstance(skill, str):
            continue

        normalized_skill = normalize_text(skill)

        if normalized_skill and normalized_skill not in seen:
            required.append(skill)
            seen.add(normalized_skill)

    matching_skills = [
        skill
        for skill in required
        if normalize_text(skill) in resume_lookup
    ]

    missing_skills = [
        skill
        for skill in required
        if normalize_text(skill) not in resume_lookup
    ]

    if required:
        skill_score = round(
            len(matching_skills) / len(required) * 100, 2
        )
    else:
        skill_score = 0.0

    return {
        "skill_score": skill_score,
        "matching_skills": matching_skills,
        "missing_skills": missing_skills,
    }
