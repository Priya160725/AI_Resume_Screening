
import os
import tempfile
import pymupdf

from resume_parser import extract_resume_text
from matching import calculate_match


pdf_path = None

try:
    # Create a temporary fictional resume PDF
    file_descriptor, pdf_path = tempfile.mkstemp(suffix=".pdf")
    os.close(file_descriptor)

    document = pymupdf.open()
    page = document.new_page()

    sample_resume = """
    ALEX MORGAN

    CAREER OBJECTIVE
    Seeking an entry-level Python Developer position.

    TECHNICAL SKILLS
    Python, Flask, SQL, Machine Learning, Git.

    PROJECTS
    Developed a web application using Python and Flask.
    Used SQL for database management.
    Applied Machine Learning concepts.

    EDUCATION
    Bachelor of Technology in Computer Science.
    """

    page.insert_text((72, 72), sample_resume)
    document.save(pdf_path)
    document.close()

    # Extract resume text
    resume_text = extract_resume_text(pdf_path)

    assert resume_text.strip(), "Resume extraction failed."

    # Sample job description
    job_description = """
    We are looking for a Python developer with skills in Python,
    Flask, SQL, Machine Learning and Natural Language Processing.
    """

    # Calculate matching score
    result = calculate_match(resume_text, job_description)

    print("Matching test successful!")
    print("Overall match:", result["match_score"], "%")
    print("Similarity:", result["similarity_score"], "%")
    print("Skill score:", result["skill_score"], "%")
    print("Matching skills:", result["matching_skills"])
    print("Missing skills:", result["missing_skills"])

except Exception as error:
    print("Matching test failed:", error)
    raise

finally:
    # Remove temporary PDF
    if pdf_path and os.path.exists(pdf_path):
        os.remove(pdf_path)
