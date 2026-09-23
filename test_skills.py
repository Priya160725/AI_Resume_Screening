from skills import extract_skills


text = """
I am a Python developer with experience in Flask,
MySQL, Machine Learning, NLP, Git and GitHub.
"""


skills = extract_skills(text)

print("Skills found:")

for skill in skills:
    print("-", skill)