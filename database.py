import os

import mysql.connector

from dotenv import load_dotenv


# =========================================================
# LOAD ENVIRONMENT VARIABLES
# =========================================================

load_dotenv()


# =========================================================
# MYSQL CONNECTION
# =========================================================

def get_connection():

    connection = mysql.connector.connect(

        host=os.getenv(
            "MYSQL_HOST"
        ),

        user=os.getenv(
            "MYSQL_USER"
        ),

        password=os.getenv(
            "MYSQL_PASSWORD"
        ),

        database=os.getenv(
            "MYSQL_DATABASE"
        )

    )

    return connection


# =========================================================
# SAVE CANDIDATE
# =========================================================

def save_candidate(

    filename,

    job_title,

    overall_score,

    similarity_score,

    skill_score,

    matching_skills,

    missing_skills

):

    connection = None

    cursor = None

    try:

        connection = get_connection()

        cursor = connection.cursor()


        # -------------------------------------------------
        # CHECK FOR DUPLICATE
        # -------------------------------------------------

        check_query = """

        SELECT id

        FROM candidates

        WHERE filename = %s

        AND job_title = %s

        LIMIT 1

        """


        cursor.execute(

            check_query,

            (
                filename,
                job_title
            )

        )


        existing_candidate = cursor.fetchone()


        if existing_candidate:

            print(
                "Candidate already exists."
            )

            print(
                "Duplicate record was NOT created."
            )

            print(
                "Filename:",
                filename
            )

            return False


        # -------------------------------------------------
        # CONVERT SKILLS TO TEXT
        # -------------------------------------------------

        if isinstance(
            matching_skills,
            list
        ):

            matching_skills_text = ", ".join(
                matching_skills
            )

        else:

            matching_skills_text = str(
                matching_skills
            )


        if isinstance(
            missing_skills,
            list
        ):

            missing_skills_text = ", ".join(
                missing_skills
            )

        else:

            missing_skills_text = str(
                missing_skills
            )


        # -------------------------------------------------
        # INSERT CANDIDATE
        # -------------------------------------------------

        insert_query = """

        INSERT INTO candidates (

            filename,

            job_title,

            overall_score,

            similarity_score,

            skill_score,

            matching_skills,

            missing_skills

        )

        VALUES (

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

                filename,

                job_title,

                overall_score,

                similarity_score,

                skill_score,

                matching_skills_text,

                missing_skills_text

            )

        )


        connection.commit()


        print(
            "Candidate saved to MySQL."
        )


        return True


    except mysql.connector.Error as error:

        print(
            "MySQL error while saving candidate:"
        )

        print(error)

        return False


    finally:

        if cursor:

            cursor.close()

        if connection:

            connection.close()


# =========================================================
# GET ALL CANDIDATES
# =========================================================

def get_all_candidates():

    connection = None

    cursor = None

    try:

        connection = get_connection()

        cursor = connection.cursor(
            dictionary=True
        )


        query = """

        SELECT

            id,

            filename,

            job_title,

            overall_score,

            similarity_score,

            skill_score,

            matching_skills,

            missing_skills,

            screened_at

        FROM candidates

        ORDER BY overall_score DESC

        """


        cursor.execute(query)


        candidates = cursor.fetchall()


        return candidates


    except mysql.connector.Error as error:

        print(
            "MySQL error while retrieving candidates:"
        )

        print(error)

        return []


    finally:

        if cursor:

            cursor.close()

        if connection:

            connection.close()


# =========================================================
# GET ONE CANDIDATE BY ID
# =========================================================

def get_candidate_by_id(candidate_id):

    connection = None

    cursor = None

    try:

        connection = get_connection()

        cursor = connection.cursor(
            dictionary=True
        )


        query = """

        SELECT

            id,

            filename,

            job_title,

            overall_score,

            similarity_score,

            skill_score,

            matching_skills,

            missing_skills,

            screened_at

        FROM candidates

        WHERE id = %s

        LIMIT 1

        """


        cursor.execute(

            query,

            (candidate_id,)

        )


        candidate = cursor.fetchone()


        return candidate


    except mysql.connector.Error as error:

        print(
            "Error retrieving candidate:"
        )

        print(error)

        return None


    finally:

        if cursor:

            cursor.close()

        if connection:

            connection.close()


# =========================================================
# DASHBOARD STATISTICS
# =========================================================

def get_dashboard_stats():

    connection = None

    cursor = None

    try:

        connection = get_connection()

        cursor = connection.cursor()


        # -------------------------------------------------
        # TOTAL CANDIDATES
        # -------------------------------------------------

        cursor.execute("""

            SELECT COUNT(*)

            FROM candidates

        """)


        total_candidates = cursor.fetchone()[0]


        # -------------------------------------------------
        # AVERAGE SCORE
        # -------------------------------------------------

        cursor.execute("""

            SELECT COALESCE(

                AVG(overall_score),

                0

            )

            FROM candidates

        """)


        average_score = cursor.fetchone()[0]


        # -------------------------------------------------
        # GOOD MATCHES
        # -------------------------------------------------

        cursor.execute("""

            SELECT COUNT(*)

            FROM candidates

            WHERE overall_score >= 60

        """)


        good_matches = cursor.fetchone()[0]


        # -------------------------------------------------
        # AVERAGE MATCHES
        # -------------------------------------------------

        cursor.execute("""

            SELECT COUNT(*)

            FROM candidates

            WHERE overall_score >= 40

            AND overall_score < 60

        """)


        average_matches = cursor.fetchone()[0]


        # -------------------------------------------------
        # LOW MATCHES
        # -------------------------------------------------

        cursor.execute("""

            SELECT COUNT(*)

            FROM candidates

            WHERE overall_score < 40

        """)


        low_matches = cursor.fetchone()[0]


        return {

            "total_candidates":
                total_candidates,

            "average_score":
                float(
                    average_score
                ),

            "good_matches":
                good_matches,

            "average_matches":
                average_matches,

            "low_matches":
                low_matches

        }


    except mysql.connector.Error as error:

        print(
            "Dashboard statistics error:"
        )

        print(error)


        return {

            "total_candidates": 0,

            "average_score": 0,

            "good_matches": 0,

            "average_matches": 0,

            "low_matches": 0

        }


    finally:

        if cursor:

            cursor.close()

        if connection:

            connection.close()


# =========================================================
# TEST DATABASE CONNECTION
# =========================================================

if __name__ == "__main__":

    try:

        connection = get_connection()

        print(
            "MySQL connection successful!"
        )

        connection.close()


    except mysql.connector.Error as error:

        print(
            "MySQL connection failed."
        )

        print(error)