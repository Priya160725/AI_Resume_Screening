from resume_parser import extract_text_from_pdf

pdf_path = "uploads/Priya_Vaidya_Resume.pdf"

text = extract_text_from_pdf(pdf_path)

print(text)