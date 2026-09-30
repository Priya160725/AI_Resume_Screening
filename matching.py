import re

from sklearn.feature_extraction.text import TfidfVectorizer

from sklearn.metrics.pairwise import cosine_similarity


# ==========================================================
# SKILL LIST
# ==========================================================

SKILLS = [

    "Python",
    "Java",
    "JavaScript",
    "HTML",
    "CSS",

    "Flask",
    "Django",

    "SQL",
    "MySQL",

    "PostgreSQL",

    "Machine Learning",
    "Deep Learning",

    "Natural Language Processing",
    "NLP",

    "NLTK",
    "spaCy",

    "Scikit-learn",

    "Pandas",
    "NumPy",

    "TensorFlow",
    "PyTorch",

    "TF-IDF",

    "Cosine Similarity",

    "REST API",

    "Git",
    "GitHub",

    "Docker",

    "AWS",

    "C++",
    "C"

]


# ==========================================================
# NORMALIZE TEXT
# ==========================================================

def normalize_text(text):

    if not text:

        return ""

    text = text.lower()

    text = re.sub(
        r"[^a-z0-9+#.\- ]",
        " ",
        text
    )

    text = re.sub(
        r"\s+",
        " ",
        text
    )

    return text.strip()


# ==========================================================
# FIND SKILLS
# ==========================================================

def find_skills(text):

    normalized = normalize_text(text)

    found = []


    for skill in SKILLS:

        skill_normalized = normalize_text(
            skill
        )


        if skill_normalized in normalized:

            found.append(skill)


    return found


# ==========================================================
# CALCULATE MATCH
# ==========================================================

def calculate_match(
    resume_text,
    job_description
):


    resume_text = resume_text or ""

    job_description = job_description or ""


    # ------------------------------------------------------
    # TF-IDF SIMILARITY
    # ------------------------------------------------------

    try:

        vectorizer = TfidfVectorizer(
            stop_words="english"
        )


        vectors = vectorizer.fit_transform(

            [
                resume_text,
                job_description
            ]

        )


        similarity = cosine_similarity(

            vectors[0:1],

            vectors[1:2]

        )[0][0]


        similarity_score = round(
            similarity * 100,
            2
        )


    except Exception:

        similarity_score = 0.0


    # ------------------------------------------------------
    # SKILLS
    # ------------------------------------------------------

    resume_skills = find_skills(
        resume_text
    )


    job_skills = find_skills(
        job_description
    )


    matching_skills = [

        skill

        for skill in job_skills

        if skill in resume_skills

    ]


    missing_skills = [

        skill

        for skill in job_skills

        if skill not in resume_skills

    ]


    # ------------------------------------------------------
    # SKILL SCORE
    # ------------------------------------------------------

    if len(job_skills) > 0:

        skill_score = round(

            (
                len(matching_skills)
                /
                len(job_skills)
            )
            * 100,

            2

        )

    else:

        skill_score = similarity_score


    # ------------------------------------------------------
    # FINAL SCORE
    # ------------------------------------------------------

    match_score = round(

        (
            similarity_score * 0.5
            +
            skill_score * 0.5
        ),

        2

    )


    return {

        "match_score": match_score,

        "similarity_score": similarity_score,

        "skill_score": skill_score,

        "matching_skills": matching_skills,

        "missing_skills": missing_skills

    }