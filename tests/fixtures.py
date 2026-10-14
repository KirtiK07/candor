RESUME_TEXT = """Priya Sharma
priya.sharma@example.com | +91 98765 43210 | Pune, India | linkedin.com/in/priyasharma

SUMMARY
Software engineer with 3 years of experience building backend services in Python.

EXPERIENCE
Software Engineer, Acme Analytics, Pune — Jul 2022 – Present
• Built REST APIs in Python (Flask) serving 2 million requests per day
• Reduced report generation time by 40% by optimizing PostgreSQL queries
• Assisted in migrating services to Docker containers on AWS EC2

Junior Developer, BrightSoft Solutions, Mumbai — Jun 2021 – Jun 2022
• Wrote automation scripts in Python to clean CSV data for the analytics team
• Fixed bugs in an internal Django dashboard

EDUCATION
B.E. in Computer Engineering, Savitribai Phule Pune University — 2017 – 2021, CGPA 8.2

SKILLS
Python, Flask, Django, PostgreSQL, Docker, AWS EC2, Git, Linux

CERTIFICATIONS
AWS Certified Cloud Practitioner — Amazon Web Services, 2023
"""

JD_TEXT = """Backend Engineer – Payments Platform, FinNova Technologies (Bengaluru)

We are looking for a Backend Engineer with 2-4 years of experience to build scalable microservices.
Requirements:
- Strong Python skills (FastAPI or Flask)
- Experience designing RESTful APIs
- PostgreSQL and query optimization
- Docker and Kubernetes
- AWS (EC2, S3, Lambda)
- Experience with Kafka or other message queues is a plus
- CI/CD pipelines
Please include your notice period in your application.
"""

RESUME_JSON = {
    "name": "Priya Sharma",
    "headline": "",
    "contact": {"email": "priya.sharma@example.com", "phone": "+91 98765 43210", "location": "Pune, India",
                "linkedin": "linkedin.com/in/priyasharma", "github": "", "portfolio": "", "other": []},
    "summary": "Software engineer with 3 years of experience building backend services in Python.",
    "skills": [{"category": "", "items": ["Python", "Flask", "Django", "PostgreSQL", "Docker", "AWS EC2", "Git", "Linux"]}],
    "experience": [
        {"company": "Acme Analytics", "title": "Software Engineer", "location": "Pune", "start": "Jul 2022",
         "end": "Present", "bullets": ["Built REST APIs in Python (Flask) serving 2 million requests per day",
                                       "Reduced report generation time by 40% by optimizing PostgreSQL queries",
                                       "Assisted in migrating services to Docker containers on AWS EC2"]},
        {"company": "BrightSoft Solutions", "title": "Junior Developer", "location": "Mumbai", "start": "Jun 2021",
         "end": "Jun 2022", "bullets": ["Wrote automation scripts in Python to clean CSV data for the analytics team",
                                        "Fixed bugs in an internal Django dashboard"]},
    ],
    "projects": [],
    "education": [{"institution": "Savitribai Phule Pune University", "degree": "B.E.", "field": "Computer Engineering",
                   "location": "", "start": "2017", "end": "2021", "grade": "CGPA 8.2", "details": []}],
    "certifications": [{"name": "AWS Certified Cloud Practitioner", "issuer": "Amazon Web Services", "date": "2023"}],
    "achievements": [],
    "additional_sections": [],
    "section_order": ["summary", "experience", "education", "skills", "certifications"],
}

JD_ANALYSIS = {
    "job_title": "Backend Engineer", "company": "FinNova Technologies",
    "must_have_skills": ["Python", "RESTful APIs", "PostgreSQL", "Docker", "Kubernetes", "AWS"],
    "nice_to_have_skills": ["Kafka"],
    "keywords": ["FastAPI", "Flask", "microservices", "CI/CD", "query optimization", "Lambda", "S3"],
    "responsibilities": ["Build scalable microservices"],
    "jd_special_requirements": ["Include notice period"],
    "gap_analysis": {"matched": [{"requirement": "Python", "evidence": "Acme"}],
                     "transferable": [], "missing": [{"requirement": "Kubernetes", "advice": "Learn it"}]},
}
