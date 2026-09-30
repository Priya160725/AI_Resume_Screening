from flask import Flask, render_template, request
import os

from resume_parser import extract_resume_text
from matching import calculate_match


app = Flask(__name__)

UPLOAD_FOLDER = "uploads"

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

os.makedirs(UPLOAD_FOLDER, exist_ok=True)


# Stores the latest screening results
candidate_results = {}


# ---------------------------------------------------------
# HOME PAGE
# ---------------------------------------------------------

@app.route("/")
def home():

    return render_template("index.html")


# ---------------------------------------------------------
# SCREEN MULTIPLE RESUMES
# ---------------------------------------------------------

@app.route("/screen", methods=["POST"])
def screen_resumes():

    global candidate_results

    job_title = request.form.get(
        "job_title",
        "Python Developer"
    )

    job_description = request.form.get(
        "job_description",
        ""
    )

    resumes = request.files.getlist("resumes")

    results = []


    # -----------------------------------------------------
    # PROCESS RESUMES
    # -----------------------------------------------------

    for index, resume in enumerate(resumes):

        if not resume or resume.filename == "":
            continue


        filename = resume.filename


        filepath = os.path.join(
            app.config["UPLOAD_FOLDER"],
            filename
        )


        resume.save(filepath)


        # -------------------------------------------------
        # EXTRACT TEXT
        # -------------------------------------------------

        try:

            resume_text = extract_resume_text(
                filepath
            )

        except Exception as e:

            print(
                "Resume extraction error:",
                e
            )

            continue


        # -------------------------------------------------
        # CALCULATE MATCH
        # -------------------------------------------------

        try:

            match_result = calculate_match(
                resume_text,
                job_description
            )

        except Exception as e:

            print(
                "Matching error:",
                e
            )

            continue


        # -------------------------------------------------
        # READ MATCH RESULT
        # -------------------------------------------------

        if isinstance(match_result, dict):

            overall_score = match_result.get(
                "score",
                match_result.get(
                    "match_score",
                    match_result.get(
                        "overall_score",
                        0
                    )
                )
            )


            similarity_score = match_result.get(
                "similarity",
                match_result.get(
                    "similarity_score",
                    0
                )
            )


            skill_score = match_result.get(
                "skill_match",
                match_result.get(
                    "skill_score",
                    0
                )
            )


            matching_skills = match_result.get(
                "matching_skills",
                match_result.get(
                    "matched_skills",
                    []
                )
            )


            missing_skills = match_result.get(
                "missing_skills",
                []
            )


        else:

            overall_score = float(
                match_result
            )

            similarity_score = 0

            skill_score = 0

            matching_skills = []

            missing_skills = []


        # -------------------------------------------------
        # CREATE CANDIDATE
        # -------------------------------------------------

        candidate = {

            "id": index + 1,

            "filename": filename,

            "score": float(
                overall_score
            ),

            "similarity": float(
                similarity_score
            ),

            "skill_match": float(
                skill_score
            ),

            "matching_skills":
                matching_skills,

            "missing_skills":
                missing_skills,

            "job_title":
                job_title,

            "job_description":
                job_description

        }


        results.append(candidate)


    # -----------------------------------------------------
    # SORT RESULTS
    # -----------------------------------------------------

    results.sort(

        key=lambda x:
        x["score"],

        reverse=True

    )


    # -----------------------------------------------------
    # REASSIGN RANK / ID
    # -----------------------------------------------------

    for position, candidate in enumerate(
        results,
        start=1
    ):

        candidate["id"] = position


    # -----------------------------------------------------
    # SAVE RESULTS
    # -----------------------------------------------------

    candidate_results = {

        candidate["id"]:
            candidate

        for candidate in results

    }


    # -----------------------------------------------------
    # RESULT PAGE
    # -----------------------------------------------------

    return render_template(

        "result.html",

        candidates=results,

        job_title=job_title

    )


# ---------------------------------------------------------
# CANDIDATE DETAILS
# ---------------------------------------------------------

@app.route(
    "/candidate/<int:candidate_id>"
)
def candidate_details(
    candidate_id
):

    candidate = candidate_results.get(
        candidate_id
    )


    if candidate is None:

        return """
        <h2>Candidate not found</h2>
        <a href="/">Go Back</a>
        """


    return render_template(

        "candidate.html",

        candidate=candidate,

        candidate_id=candidate_id,

        filename=candidate.get(
            "filename",
            "Candidate"
        ),

        overall_score=candidate.get(
            "score",
            0
        ),

        similarity_score=candidate.get(
            "similarity",
            0
        ),

        skill_score=candidate.get(
            "skill_match",
            0
        ),

        matching_skills=candidate.get(
            "matching_skills",
            []
        ),

        missing_skills=candidate.get(
            "missing_skills",
            []
        ),

        job_title=candidate.get(
            "job_title",
            ""
        )

    )


# ---------------------------------------------------------
# RUN APPLICATION
# ---------------------------------------------------------

if __name__ == "__main__":

    app.run(

        host="127.0.0.1",

        port=5001,

        debug=True

    )