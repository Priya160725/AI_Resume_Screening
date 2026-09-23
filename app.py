from flask import Flask, render_template, request
import os
import mysql.connector
from dotenv import load_dotenv

from resume_parser import extract_text_from_pdf
from matching import calculate_match


# ==========================================================
# LOAD ENVIRONMENT VARIABLES
# ==========================================================

load_dotenv()


# ==========================================================
# FLASK APP
# ==========================================================

app = Flask(__name__)

UPLOAD_FOLDER = "uploads"

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

os.makedirs(UPLOAD_FOLDER, exist_ok=True)


# ==========================================================
# MYSQL CONNECTION
# ==========================================================

def get_connection():

    return mysql.connector.connect(
        host=os.getenv("MYSQL_HOST"),
        user=os.getenv("MYSQL_USER"),
        password=os.getenv("MYSQL_PASSWORD"),
        database=os.getenv("MYSQL_DATABASE")
    )


# ==========================================================
# HOME
# ==========================================================

@app.route("/")
def home():

    return render_template("index.html")


# ==========================================================
# SCREEN RESUMES
# ==========================================================

@app.route("/screen", methods=["POST"])
def screen_resumes():

    job_title = request.form.get(
        "job_title",
        ""
    ).strip()

    job_description = request.form.get(
        "job_description",
        ""
    ).strip()


    if not job_title:

        return "Please enter a job title.", 400


    if not job_description:

        return "Please enter a job description.", 400


    files = request.files.getlist("resumes")

    files = [
        file
        for file in files
        if file and file.filename
    ]


    if not files:

        return "Please upload at least one PDF resume.", 400


    # ======================================================
    # DATABASE CONNECTION
    # ======================================================

    connection = get_connection()

    cursor = connection.cursor(
        dictionary=True
    )


    results = []


    # ======================================================
    # PROCESS EACH RESUME
    # ======================================================

    for file in files:

        # --------------------------------------------------
        # ONLY PDF FILES
        # --------------------------------------------------

        if not file.filename.lower().endswith(".pdf"):

            continue


        filename = file.filename


        # --------------------------------------------------
        # SAVE RESUME
        # --------------------------------------------------

        file_path = os.path.join(
            app.config["UPLOAD_FOLDER"],
            filename
        )

        file.save(file_path)


        # --------------------------------------------------
        # EXTRACT TEXT FROM PDF
        # --------------------------------------------------

        resume_text = extract_text_from_pdf(
            file_path
        )


        # --------------------------------------------------
        # CALCULATE MATCH
        # --------------------------------------------------

        match_result = calculate_match(
            resume_text,
            job_description
        )


        match_score = float(
            match_result.get(
                "match_score",
                0
            )
        )


        similarity_score = float(
            match_result.get(
                "similarity_score",
                match_score
            )
        )


        skill_score = float(
            match_result.get(
                "skill_score",
                match_score
            )
        )


        matching_skills = match_result.get(
            "matching_skills",
            []
        )


        missing_skills = match_result.get(
            "missing_skills",
            []
        )


        # ==================================================
        # CONVERT SKILLS TO LIST
        # ==================================================

        if isinstance(
            matching_skills,
            str
        ):

            matching_skills = [
                skill.strip()
                for skill in matching_skills.split(",")
                if skill.strip()
            ]


        if isinstance(
            missing_skills,
            str
        ):

            missing_skills = [
                skill.strip()
                for skill in missing_skills.split(",")
                if skill.strip()
            ]


        # ==================================================
        # MATCH CATEGORY
        # ==================================================

        if match_score >= 70:

            match_category = "Good Match"

        elif match_score >= 40:

            match_category = "Average Match"

        else:

            match_category = "Low Match"


        # ==================================================
        # DATABASE SKILL FORMAT
        # ==================================================

        matching_skills_db = ", ".join(
            matching_skills
        )

        missing_skills_db = ", ".join(
            missing_skills
        )


        # ==================================================
        # INSERT CANDIDATE INTO DATABASE
        # ==================================================

        insert_query = """

            INSERT INTO candidates
            (
                job_title,
                filename,
                match_score,
                similarity_score,
                skill_score,
                match_category,
                matching_skills,
                missing_skills
            )

            VALUES
            (
                %s,
                %s,
                %s,
                %s,
                %s,
                %s,
                %s,
                %s
            )

        """


        cursor.execute(
            insert_query,
            (
                job_title,
                filename,
                match_score,
                similarity_score,
                skill_score,
                match_category,
                matching_skills_db,
                missing_skills_db
            )
        )


        candidate_id = cursor.lastrowid


        # ==================================================
        # ADD RESULT
        # ==================================================

        results.append({

            "id": candidate_id,

            "job_title": job_title,

            "filename": filename,

            "match_score": match_score,

            "similarity_score": similarity_score,

            "skill_score": skill_score,

            "match_category": match_category,

            "matching_skills": matching_skills,

            "missing_skills": missing_skills

        })


    # ======================================================
    # SAVE DATABASE CHANGES
    # ======================================================

    connection.commit()

    cursor.close()

    connection.close()


    # ======================================================
    # SHOW RESULTS
    # ======================================================

    return render_template(
        "result.html",
        candidates=results,
        job_title=job_title
    )


# ==========================================================
# DASHBOARD
# ==========================================================

@app.route("/dashboard")
def dashboard():

    connection = get_connection()

    cursor = connection.cursor(
        dictionary=True
    )


    query = """

        SELECT
            id,
            job_title,
            filename,
            match_score,
            similarity_score,
            skill_score,
            match_category,
            matching_skills,
            missing_skills,
            screened_at

        FROM candidates

        ORDER BY match_score DESC

    """


    cursor.execute(query)

    candidates = cursor.fetchall()


    cursor.close()

    connection.close()


    # ======================================================
    # CONVERT DATABASE SKILLS TO LISTS
    # ======================================================

    for candidate in candidates:

        matching = candidate.get(
            "matching_skills"
        )

        missing = candidate.get(
            "missing_skills"
        )


        if matching:

            candidate["matching_skills"] = [
                skill.strip()
                for skill in matching.split(",")
                if skill.strip()
            ]

        else:

            candidate["matching_skills"] = []


        if missing:

            candidate["missing_skills"] = [
                skill.strip()
                for skill in missing.split(",")
                if skill.strip()
            ]

        else:

            candidate["missing_skills"] = []


    return render_template(
        "dashboard.html",
        candidates=candidates
    )


# ==========================================================
# CANDIDATE DETAILS
# ==========================================================

@app.route("/candidate/<int:candidate_id>")
def candidate_details(candidate_id):

    connection = get_connection()

    cursor = connection.cursor(
        dictionary=True
    )


    query = """

        SELECT
            id,
            job_title,
            filename,
            match_score,
            similarity_score,
            skill_score,
            match_category,
            matching_skills,
            missing_skills,
            screened_at

        FROM candidates

        WHERE id = %s

    """


    cursor.execute(
        query,
        (candidate_id,)
    )


    candidate = cursor.fetchone()


    cursor.close()

    connection.close()


    if candidate is None:

        return "Candidate not found.", 404


    # ======================================================
    # MATCHING SKILLS
    # ======================================================

    matching = candidate.get(
        "matching_skills"
    )


    if matching:

        candidate["matching_skills"] = [
            skill.strip()
            for skill in matching.split(",")
            if skill.strip()
        ]

    else:

        candidate["matching_skills"] = []


    # ======================================================
    # MISSING SKILLS
    # ======================================================

    missing = candidate.get(
        "missing_skills"
    )


    if missing:

        candidate["missing_skills"] = [
            skill.strip()
            for skill in missing.split(",")
            if skill.strip()
        ]

    else:

        candidate["missing_skills"] = []


    return render_template(
        "candidate.html",
        candidate=candidate
    )


# ==========================================================
# RUN FLASK APPLICATION
# ==========================================================

if __name__ == "__main__":

    app.run(
        host="127.0.0.1",
        port=5001,
        debug=True
    )