# TalentLens AI
## AI-Powered Resume Screening and Candidate Ranking System Using Natural Language Processing (NLP)

### 1. Project Overview

TalentLens AI is a web-based resume screening and candidate ranking application developed using Python, Flask, Natural Language Processing (NLP) techniques and MySQL.

The application helps recruiters evaluate multiple candidates by comparing uploaded resumes against a job description. It identifies matching and missing skills, calculates candidate match scores and ranks candidates based on their suitability for a job.

### 2. Project Objectives

- Automate the initial resume screening process.
- Extract information from PDF, DOCX and TXT resumes.
- Compare resumes with job descriptions.
- Identify matching and missing skills.
- Calculate resume similarity and skill match scores.
- Rank candidates according to their overall match scores.
- Provide candidate profiles and screening history.
- Help candidates identify skill gaps and track learning progress.

### 3. Main Features

**Resume Screening**
- Upload multiple resumes.
- Support PDF, DOCX and TXT formats.
- Extract resume text.
- Compare resumes against a job description.
- Prevent duplicate resume submissions for the same job.

**AI-Based Matching and Ranking**
- TF-IDF text vectorization.
- Cosine similarity calculation.
- Skill extraction and matching.
- Matching and missing skill identification.
- Overall match score calculation.
- Automatic candidate ranking.

**Candidate Management**
- Candidate details and screening results.
- Candidate profiles.
- Screening history.
- Candidate comparison.
- CSV report exports.

**Skill Development and Analytics**
- Candidate skill progress tracking.
- Private candidate progress portal.
- Skill-gap analysis.
- Learning analytics dashboard.
- Learning progress export.

**System and Security**
- MySQL database integration.
- Health-check endpoint.
- Database connection test.
- CSRF protection.
- Secure filename handling.
- File type and upload size validation.
- Parameterized SQL queries.

### 4. Technologies Used

| Area | Technologies |
|---|---|
| Frontend | HTML, CSS, JavaScript |
| Backend | Python, Flask |
| Machine Learning | scikit-learn |
| Text Processing | TF-IDF, Cosine Similarity |
| Resume Processing | PyMuPDF, python-docx |
| Database | MySQL |
| Security | Flask-WTF, CSRF protection |
| Development | VS Code, Git |

### 5. Candidate Scoring Method

The system calculates the overall candidate match score using two components:

- Resume similarity: 40%
- Skill matching score: 60%

**Formula:**

Overall Match Score = (Similarity Score × 0.40) + (Skill Score × 0.60)

Candidate categories:

- Strong Match: 75% and above
- Moderate Match: 50% to below 75%
- Low Match: Below 50%

### 6. System Workflow

1. Recruiter opens the TalentLens AI application.
2. Recruiter enters a job title and job description.
3. Recruiter uploads candidate resumes.
4. The application extracts resume text.
5. The system identifies relevant skills.
6. TF-IDF and cosine similarity compare resume content with the job description.
7. The system calculates the overall match score.
8. Candidates are ranked according to their scores.
9. Recruiter views candidate details, matching skills and missing skills.
10. Candidate progress and learning analytics can be reviewed.

### 7. Project Architecture

Recruiter
↓
Web Interface (HTML, CSS, JavaScript)
↓
Flask Backend
↓
Resume Upload and Text Extraction
↓
NLP-Based Skill Analysis
↓
TF-IDF and Cosine Similarity
↓
Skill Matching and Score Calculation
↓
Candidate Ranking
↓
MySQL Database
↓
Dashboard, Candidate Profiles and Analytics

### 8. Project Requirements

- Python 3
- MySQL Server
- pip
- Visual Studio Code or another code editor
- A modern web browser

### 9. Installation and Setup

Clone or download the project and open its directory:

```bash
cd ~/AI_Resume_Screening
```

Create a virtual environment:

```bash
python3 -m venv venv
```

Activate it:

```bash
source venv/bin/activate
```

Install the required packages:

```bash
pip install -r requirements.txt
```

### 10. Database Configuration

Make sure MySQL Server is running.

Create the project database if it does not already exist:

```sql
CREATE DATABASE IF NOT EXISTS ai_resume_screening;
```

The application initializes its required tables when it starts.

### 11. Environment Variables

Create a `.env` file in the project root directory.

Add the following configuration, replacing the placeholders with your own local MySQL settings:

```env
MYSQL_HOST=localhost
MYSQL_USER=root
MYSQL_PASSWORD=your_mysql_password
MYSQL_DATABASE=ai_resume_screening
FLASK_SECRET_KEY=your_long_random_secret_key
```

Keep `.env` private. Never upload passwords or secret keys to GitHub.

### 12. Run the Application

From the project directory, run:

```bash
./venv/bin/python app.py
```

Open the application in your browser:

**Home:** http://127.0.0.1:5001/

**Dashboard:** http://127.0.0.1:5001/dashboard

**History:** http://127.0.0.1:5001/history

**Candidate Comparison:** http://127.0.0.1:5001/compare

**Learning Analytics:** http://127.0.0.1:5001/learning-analytics

**System Health:** http://127.0.0.1:5001/health

**Database Test:** http://127.0.0.1:5001/test-db

### 13. Testing

Run the project tests from the project directory:

```bash
./venv/bin/python test_database.py
./venv/bin/python test_parser.py
./venv/bin/python test_skills.py
./venv/bin/python test_matching.py
```

Check Python syntax:

```bash
./venv/bin/python -m py_compile app.py matching.py
```

### 14. File Upload Limits

- Supported formats: PDF, DOCX and TXT.
- Maximum individual resume size: 5 MB.
- Maximum total request size: 50 MB.
- Scanned PDFs without extractable text may not be processed because OCR is not currently implemented.

### 15. Future Enhancements

- OCR support for scanned resumes.
- Improved semantic understanding of job descriptions.
- Advanced NLP-based skill extraction.
- Additional candidate recommendation features.
- More comprehensive automated testing.
- Cloud deployment and production configuration.

### 16. Conclusion

TalentLens AI demonstrates how NLP and machine learning techniques can support automated resume screening and candidate ranking. It provides recruiters with structured candidate comparisons, skill analysis and progress tracking through a web-based application.

The project aims to make the initial recruitment screening process more organized, efficient and understandable.