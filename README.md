# AI-Powered Resume Screening and Candidate Ranking System Using NLP

## 📌 Project Overview

The AI-Powered Resume Screening and Candidate Ranking System is a web-based application designed to help recruiters screen and rank multiple candidates automatically.

The system compares uploaded resumes with a given job description using Natural Language Processing (NLP), resume similarity, and skill matching techniques.

It calculates an overall match score and ranks candidates based on their matching skills and resume content.

---

## 🎯 Objectives

- Automatically screen multiple resumes.
- Extract text from PDF and DOCX resumes.
- Compare resumes with a job description.
- Identify matching skills.
- Identify missing skills.
- Calculate resume similarity.
- Calculate skill match percentage.
- Rank candidates based on their overall match score.
- Provide candidate-level screening details.

---

## 🚀 Main Features

### Multiple Resume Upload

Recruiters can upload multiple resumes at the same time for screening.

### Resume Text Extraction

The system extracts text from:

- PDF files
- DOCX files

### NLP-Based Resume Analysis

The extracted resume content is processed and compared with the job description.

### Resume Similarity

The system calculates the similarity between the resume and the job description using text-based similarity techniques.

### Skill Matching

The system identifies:

- Matching skills
- Missing skills
- Skill match percentage

### Candidate Ranking

Candidates are automatically ranked according to their overall match score.

### Candidate Details

Recruiters can view individual candidate screening information including:

- Overall match score
- Resume similarity
- Skill match
- Matching skills
- Missing skills

---

## 🛠 Technologies Used

### Frontend

- HTML
- CSS
- JavaScript

### Backend

- Python
- Flask

### NLP and Machine Learning

- NLTK
- spaCy
- scikit-learn
- TF-IDF
- Cosine Similarity

### Resume Processing

- PyMuPDF
- python-docx

### Database

- MySQL

### Development Tools

- Visual Studio Code
- Git
- GitHub

---

## 🏗 System Workflow

```text
Recruiter
    ↓
Web Interface
    ↓
Upload Multiple Resumes + Job Description
    ↓
Resume Text Extraction
    ↓
NLP Processing
    ↓
Skill Extraction and Matching
    ↓
TF-IDF + Cosine Similarity
    ↓
Overall Match Score
    ↓
Candidate Ranking
    ↓
Candidate Details
