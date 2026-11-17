
import re
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


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


def find_skills(text):
    normalized = normalize_text(text)
    found = []

    for skill in SKILLS:
        skill_normalized = normalize_text(skill)

        if not skill_normalized:
            continue

        # Match skill names without matching them inside larger words.
        pattern = r"(?<![a-z0-9])" + re.escape(skill_normalized) + r"(?![a-z0-9])"

        if re.search(pattern, normalized):
            found.append(skill)

    return found


def calculate_match(resume_text, job_description):
    resume_text = resume_text if isinstance(resume_text, str) else ""
    job_description = (
        job_description if isinstance(job_description, str) else ""
    )

    similarity_score = 0.0

    if resume_text.strip() and job_description.strip():
        try:
            vectorizer = TfidfVectorizer(stop_words="english")
            vectors = vectorizer.fit_transform(
                [resume_text, job_description]
            )

            similarity = cosine_similarity(
                vectors[0:1], vectors[1:2]
            )[0][0]

            similarity_score = round(float(similarity) * 100, 2)
        except ValueError:
            similarity_score = 0.0
        except Exception as error:
            print("Similarity calculation error:", error)
            similarity_score = 0.0

    resume_skills = find_skills(resume_text)
    job_skills = find_skills(job_description)

    matching_skills = [
        skill for skill in job_skills if skill in resume_skills
    ]
    missing_skills = [
        skill for skill in job_skills if skill not in resume_skills
    ]
    if job_skills:
        skill_score = round(
            len(matching_skills) / len(job_skills) * 100, 2
        )
        match_score = round(
            similarity_score * 0.4 + skill_score * 0.6, 2
        )
    else:
        skill_score = 0.0
        match_score = round(similarity_score * 0.4, 2)

    return {
        "match_score": match_score,
        "similarity_score": similarity_score,
        "skill_score": skill_score,
        "matching_skills": matching_skills,
        "missing_skills": missing_skills,
    }


def calculate_similarity(resume_text, job_description):
    result = calculate_match(resume_text, job_description)
    return result["similarity_score"]
