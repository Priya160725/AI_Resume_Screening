from resume_parser import extract_text_from_pdf
from matching import calculate_similarity


pdf_path = "uploads/Priya_Vaidya_Resume.pdf"


resume_text = extract_text_from_pdf(pdf_path)


job_description = """
We are looking for a Python developer with skills in Python,
Flask, SQL, Machine Learning and Natural Language Processing.
"""


score = calculate_similarity(
    resume_text,
    job_description
)


print("Resume Match Score:", score, "%")