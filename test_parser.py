import os
import tempfile
import pymupdf

from resume_parser import extract_resume_text


pdf_path = None

try:
    # Create a temporary fictional PDF resume
    file_descriptor, pdf_path = tempfile.mkstemp(suffix=".pdf")
    os.close(file_descriptor)
    document = pymupdf.open()
    page = document.new_page()

    sample_resume = """
    ALEX MORGAN
    Bengaluru, India

    CAREER OBJECTIVE
    Seeking an entry-level Python Developer position.

    TECHNICAL SKILLS
    Python, SQL, Flask, Machine Learning, Git.

    PROJECTS
    Created a fictional student performance analysis project
    using Python and SQL.

    EDUCATION
    Bachelor of Technology in Computer Science.
    """

    page.insert_text((72, 72), sample_resume)
    document.save(pdf_path)
    document.close()

    # Test PDF extraction
    extracted_text = extract_resume_text(pdf_path)

    assert extracted_text.strip(), "Extracted text is empty."
    assert "ALEX MORGAN" in extracted_text, "Sample name not found."
    assert "Python" in extracted_text, "Sample skill not found."

    print("PDF extraction successful!")
    print("Extracted characters:", len(extracted_text))
    print("Preview:")
    print(extracted_text[:500])

except Exception as error:
    print("PDF parser test failed:", error)
    raise

finally:
    # Delete temporary PDF
    if pdf_path and os.path.exists(pdf_path):
        os.remove(pdf_path)
