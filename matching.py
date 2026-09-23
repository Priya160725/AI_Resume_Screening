from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from skills import extract_skills


def calculate_match(resume_text, job_description):

    # --------------------------------------------------
    # SAFETY CHECK
    # --------------------------------------------------

    if not resume_text:
        resume_text = ""

    if not job_description:
        job_description = ""


    # --------------------------------------------------
    # TF-IDF + COSINE SIMILARITY
    # --------------------------------------------------

    try:

        vectorizer = TfidfVectorizer(
            stop_words="english"
        )

        vectors = vectorizer.fit_transform([
            resume_text,
            job_description
        ])

        similarity = cosine_similarity(
            vectors[0:1],
            vectors[1:2]
        )[0][0]

        similarity_score = similarity * 100

    except Exception as error:

        print("Similarity error:", error)

        similarity_score = 0.0


    # --------------------------------------------------
    # EXTRACT SKILLS
    # --------------------------------------------------

    resume_skills = extract_skills(
        resume_text
    )

    job_skills = extract_skills(
        job_description
    )


    # --------------------------------------------------
    # FIND MATCHING SKILLS
    # --------------------------------------------------

    matching_skills = []

    for job_skill in job_skills:

        for resume_skill in resume_skills:

            if job_skill.lower() == resume_skill.lower():

                matching_skills.append(
                    job_skill
                )

                break


    # --------------------------------------------------
    # FIND MISSING SKILLS
    # --------------------------------------------------

    missing_skills = []

    for job_skill in job_skills:

        found = False

        for resume_skill in resume_skills:

            if job_skill.lower() == resume_skill.lower():

                found = True

                break


        if not found:

            missing_skills.append(
                job_skill
            )


    # --------------------------------------------------
    # SKILL SCORE
    # --------------------------------------------------

    if len(job_skills) > 0:

        skill_score = (
            len(matching_skills)
            / len(job_skills)
        ) * 100

    else:

        skill_score = 0.0


    # --------------------------------------------------
    # FINAL MATCH SCORE
    #
    # 60% similarity
    # 40% skills
    # --------------------------------------------------

    match_score = (

        similarity_score * 0.60

        +

        skill_score * 0.40

    )


    # --------------------------------------------------
    # LIMIT SCORE TO 0–100
    # --------------------------------------------------

    match_score = max(
        0,
        min(
            match_score,
            100
        )
    )


    # --------------------------------------------------
    # RETURN RESULTS
    # --------------------------------------------------

    return {

        "match_score": round(
            match_score,
            2
        ),

        "similarity_score": round(
            similarity_score,
            2
        ),

        "skill_score": round(
            skill_score,
            2
        ),

        "matching_skills":
            matching_skills,

        "missing_skills":
            missing_skills

    }