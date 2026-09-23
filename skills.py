SKILLS = [

    "Python",
    "Java",
    "C++",

    "JavaScript",
    "HTML",
    "CSS",

    "Flask",
    "Django",

    "SQL",
    "MySQL",
    "MongoDB",

    "Machine Learning",
    "Deep Learning",

    "Natural Language Processing",
    "NLP",

    "NLTK",
    "spaCy",
    "Scikit-learn",

    "TensorFlow",
    "PyTorch",

    "Pandas",
    "NumPy",

    "Git",
    "GitHub",

    "Docker",
    "AWS",

    "REST API",

    "TF-IDF",
    "Cosine Similarity"
]


def extract_skills(text):

    found_skills = []

    if not text:

        return found_skills


    text = text.lower()


    for skill in SKILLS:

        if skill.lower() in text:

            found_skills.append(
                skill
            )


    return found_skills