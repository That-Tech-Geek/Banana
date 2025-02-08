import sqlite3
import hashlib
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import docx
from PyPDF2 import PdfReader
import cohere
import streamlit as st

# Cohere API setup (ensure you have a valid API key)
cohere_api_key = st.secrets.get("API", "")
if cohere_api_key:
    try:
        co = cohere.Client(cohere_api_key)
    except Exception as e:
        st.error(f"Error initializing Cohere API: {e}")
        co = None
else:
    st.error("Cohere API key is missing.")

# Email Settings (configure your email provider)
EMAIL_ADDRESS = st.secrets.get("EMAIL-ADDRESS", "")
EMAIL_PASSWORD = st.secrets.get("EMAIL-PASSWORD", "")
SMTP_SERVER = "smtp.example.com"
SMTP_PORT = 587

# Database Setup
conn = sqlite3.connect('banana_job_platform.db', check_same_thread=False)
c = conn.cursor()

# Utility Functions
def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def authenticate_user(username, password):
    c.execute("SELECT * FROM users WHERE username=? AND password=?", (username, hash_password(password)))
    return c.fetchone()

def send_email(subject, recipient, body):
    try:
        msg = MIMEMultipart()
        msg['From'] = EMAIL_ADDRESS
        msg['To'] = recipient
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'plain'))
        
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
        server.send_message(msg)
        server.quit()
        st.success(f"Email sent to {recipient}!")
    except Exception as e:
        st.error(f"Error sending email: {e}")

# CV Text Extraction
def extract_text_from_cv(cv_file):
    if cv_file.type == "application/pdf":
        pdf_reader = PdfReader(cv_file)
        text = ""
        for page in pdf_reader.pages:
            text += page.extract_text()
        return text
    elif cv_file.type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
        doc = docx.Document(cv_file)
        text = ""
        for para in doc.paragraphs:
            text += para.text + "\n"
        return text
    else:
        return "Unsupported file type"

# Generate a Summary of the Applicant using Cohere
def generate_cv_summary(cv_text):
    if co is None:
        return "Cohere API is not available."
    
    prompt = f"Summarize the following CV text into a concise and informative summary:\n\n{cv_text}\n\nSummary:"
    try:
        response = co.generate(
            model="command",
            prompt=prompt,
            max_tokens=3000,
            temperature=0.7
        )
        
        if response and hasattr(response, 'generations') and response.generations:
            return response.generations[0].text.strip()  # Extract summary text
        else:
            return "No summary generated, please check the input data."
    except Exception as e:
        st.error(f"Error generating CV summary: {e}")
        return "Error generating summary. Please try again later."

# Generate Interview Questions using Cohere based on CV Summary and Job Description
def generate_interview_questions(summary, job_description):
    if co is None:
        return "Cohere API is not available."
    
    prompt = f"Based on the following job description and applicant's summary, generate 15 relevant interview questions:\n\nJob Description: {job_description}\n\nApplicant Summary: {summary}\n\nInterview Questions. Generate only the questions, and no other text AT ALL."
    try:
        response = co.generate(
            model="command",
            prompt=prompt,
            max_tokens=20000,
            temperature=0.7
        )
        
        if response and hasattr(response, 'generations') and response.generations:
            return response.generations[0].text.strip()  # Extract text from the first generation
        else:
            return "No questions generated, please check the input data."
    except Exception as e:
        st.error(f"Error generating interview questions: {e}")
        return "Error generating interview questions. Please try again later."

# Simple Applicant Assessment Logic
def assess_application(cv_text, job_description, interview_responses):
    # Simplified assessment logic
    score = 0
    keywords = ["Python", "communication", "leadership", "team", "experience"]
    
    # Checking if CV contains keywords
    for word in keywords:
        if word.lower() in cv_text.lower():
            score += 1
    
    # Checking if Job Description mentions key areas
    if "leadership" in job_description.lower():
        score += 1
    
    # Checking if interview responses mention critical qualities
    for response in interview_responses:
        if "leadership" in response.lower():
            score += 1
        if "communication" in response.lower():
            score += 1
    
    # Decision: If score is above a threshold, consider passing to the next round
    if score >= 5:
        return "Passed to next round"
    else:
        return "Not selected"

# Streamlit App
# README content as a string
readme_content = """
Welcome to Banana, the applicant-centric job search platform of the future.

## Features

- **Applicant-Centric Design**: Focused on providing a seamless experience for job seekers.
- **AI-Powered Assessments**: Utilize advanced AI to assess applications and provide feedback.
- **Interactive Interface**: Engage with an intuitive and user-friendly interface.

## How We Differ from Conventional Job Search Sites

Unlike traditional job search platforms, Banana offers:

- **Personalized Job Matching**: Tailored job recommendations based on your profile and preferences.
- **Real-Time Application Tracking**: Monitor the status of your applications in real-time.
- **Skill Development Resources**: Access resources to enhance your skills and improve your employability.

Join us today and take the next step in your career journey with Banana!
"""

# Display the content on the homepage
st.title("🍌 Banana: Ultimate Job Search Platform")
st.markdown(readme_content)

# Menu Navigation
menu = ["Home", "Login", "Sign Up"]
choice = st.sidebar.selectbox("Menu", menu)

# Database Initialization (Create tables if they don’t exist)
c.execute('''CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE,
                email TEXT,
                password TEXT,
                role TEXT)''')

c.execute('''CREATE TABLE IF NOT EXISTS jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                recruiter_id INTEGER,
                job_title TEXT,
                job_description TEXT,
                interview_questions TEXT,
                FOREIGN KEY (recruiter_id) REFERENCES users (id))''')

c.execute('''CREATE TABLE IF NOT EXISTS applications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                applicant_id INTEGER,
                job_id INTEGER,
                status TEXT DEFAULT 'Applied',
                responses TEXT,
                assessment TEXT,
                FOREIGN KEY (applicant_id) REFERENCES users (id),
                FOREIGN KEY (job_id) REFERENCES jobs (id))''')

conn.commit()

# Home Page
if choice == "Home":
    st.subheader("Welcome to Banana!")
    st.write("**The applicant-centric job search platform of the future.**")

# Sign-Up Page
elif choice == "Sign Up":
    st.subheader("Create an Account")
    email = st.text_input("Email")
    password = st.text_input("Password", type="password")
    role = st.radio("Register as:", ["Applicant", "Recruiter"])
    
    if st.button("Sign Up"):
        try:
            # Check if the email already exists for the chosen role
            c.execute("SELECT * FROM users WHERE email=? AND role=?", (email, role))
            existing_user = c.fetchone()
            if existing_user:
                st.error(f"An account already exists for {role} with this email. Please login or use a different email.")
            else:
                # Check if the user already has an account in the opposite role
                opposite_role = "Applicant" if role == "Recruiter" else "Recruiter"
                c.execute("SELECT * FROM users WHERE email=? AND role=?", (email, opposite_role))
                opposite_role_user = c.fetchone()
                if opposite_role_user:
                    st.error(f"An account already exists for the opposite role ({opposite_role}) with this email.")
                else:
                    # Register the user
                    username = st.text_input(f"{role} Username")
                    c.execute("INSERT INTO users (username, email, password, role) VALUES (?, ?, ?, ?)",
                              (username, email, hash_password(password), role))
                    conn.commit()
                    send_email("Job Application Confirmation", email,
                               f"Hi {username},\n\nYou have successfully created an account as a {role}. Good luck!")

        except sqlite3.IntegrityError:
            st.error("Error creating account. Please try again.")

# Login Page
elif choice == "Login":
    st.subheader("Login to Your Account")
    username = st.text_input("Username")
    password = st.text_input("Password", type="password")
    if st.button("Login"):
        user = authenticate_user(username, password)
        if user:
            # Store session data
            st.session_state["logged_in"] = True
            st.session_state["user"] = user
            st.session_state["role"] = user[4]
            st.session_state["username"] = user[1]  # Store username
            st.success(f"Welcome back, {username}!")
        else:
            st.error("Invalid username or password.")

# Dashboard After Login
if "logged_in" in st.session_state and st.session_state["logged_in"]:
    role = st.session_state["role"]
    username = st.session_state["username"]

    st.sidebar.write(f"Logged in as: {username} ({role})")

    # Applicant Dashboard
    if role == "Applicant":
        st.header("Applicant Dashboard")
        st.subheader("Available Jobs")

        # Fetch jobs from the database
        @st.cache_data
        def fetch_jobs():
            c.execute("SELECT * FROM jobs")
            return c.fetchall()

        jobs = fetch_jobs()
        for job in jobs:
            st.write(f"**{job[2]}** - {job[3]}")
            apply_button = st.button(f"Apply for {job[2]}", key=f"apply_{job[0]}")
            if apply_button:
                st.session_state["job_id"] = job[0]
                cv_file = st.file_uploader("Upload your CV", type=["pdf", "docx"])
                if cv_file:
                    cv_text = extract_text_from_cv(cv_file)
                    summary = generate_cv_summary(cv_text)
                    interview_questions = generate_interview_questions(summary, job[3])

                    st.subheader("CV Summary:")
                    st.write(summary)
                    st.subheader("Suggested Interview Questions:")
                    st.write(interview_questions)
                    responses = st.text_area("Your interview responses:", "")
                    if st.button("Submit Application"):
                        # Save the application data
                        c.execute("INSERT INTO applications (applicant_id, job_id, responses) VALUES (?, ?, ?)",
                                  (st.session_state["user"][0], job[0], responses))
                        conn.commit()
                        st.success("Application submitted!")
                        send_email("Application Confirmation", st.session_state["user"][2],
                                   f"Your application for the position '{job[2]}' has been submitted successfully.")

