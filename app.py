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
cohere_api_key = st.secrets["API"]
try:
    co = cohere.Client(cohere_api_key)
except Exception as e:
    st.error(f"Error initializing Cohere API: {e}")
    co = None

# Email Settings (configure your email provider)
EMAIL_ADDRESS = st.secrets["EMAIL-ADDRESS"]
EMAIL_PASSWORD = st.secrets["EMAIL-PASSWORD"]
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

def extract_text_from_cv(cv_file):
    if cv_file.type == "application/pdf":
        pdf_reader = PdfReader(cv_file)
        text = ""
        for page in pdf_reader.pages:
            text += page.extract_text() or ""
        return text
    elif cv_file.type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
        doc = docx.Document(cv_file)
        text = ""
        for para in doc.paragraphs:
            text += para.text + "\n"
        return text
    else:
        st.error("Unsupported file type. Please upload a PDF or DOCX file.")
        return None

def generate_cv_summary(cv_text):
    prompt = f"Summarize the following CV:\n\n{cv_text}\n\nSummary:"
    response = co.generate(
        model='xlarge',
        prompt=prompt,
        max_tokens=100,
        temperature=0.7,
        stop_sequences=["\n"]
    )
    return response.generations[0].text.strip()

def generate_questionnaire(cv_summary, job_description):
    prompt = f"Generate a set of interview questions based on the following CV summary and job description.\n\nCV Summary:\n{cv_summary}\n\nJob Description:\n{job_description}\n\nQuestions:"
    response = co.generate(
        model='xlarge',
        prompt=prompt,
        max_tokens=150,
        temperature=0.7,
        stop_sequences=["\n"]
    )
    return response.generations[0].text.strip()

# Streamlit App: Handling User Login
menu = ["Home", "Login", "Sign Up"]
choice = st.sidebar.selectbox("Menu", menu)

# Database Initialization
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
                FOREIGN KEY (recruiter_id) REFERENCES users (id))''')

c.execute('''CREATE TABLE IF NOT EXISTS applications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                applicant_id INTEGER,
                job_id INTEGER,
                status TEXT DEFAULT 'Applied',
                responses TEXT,
                assessment TEXT,
                rejection_reason TEXT,
                FOREIGN KEY (applicant_id) REFERENCES users (id),
                FOREIGN KEY (job_id) REFERENCES jobs (id))''')

conn.commit()

# Main Menu
if choice == "Home":
    st.title("🍌 Banana: Ultimate Job Search Platform")
    st.write("**The applicant-centric job search platform of the future.**")

# Sign-Up Page
elif choice == "Sign Up":
    st.subheader("Create an Account")
    email = st.text_input("Email")
    password = st.text_input("Password", type="password")
    role = st.radio("Register as:", ["Applicant", "Recruiter"])
    
    if st.button("Sign Up"):
        try:
            c.execute("SELECT * FROM users WHERE email=? AND role=?", (email, role))
            existing_user = c.fetchone()
            if existing_user:
                st.error(f"An account already exists for {role} with this email. Please login or use a different email.")
            else:
                username = st.text_input(f"{role} Username")
                if username:
                    c.execute("INSERT INTO users (username, email, password, role) VALUES (?, ?, ?, ?)",
                              (username, email, hash_password(password), role))
                    conn.commit()
                    send_email("Job Application Confirmation", email, f"Hi {username},\n\nYou have successfully created an account as a {role}. Good luck!")
                    st.success(f"Account created for {role}!")
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
            st.session_state["logged_in"] = True
            st.session_state["user"] = user
            st.session_state["role"] = user[4]
            st.session_state["username"] = user[1]
            st.success(f"Welcome back, {username}!")
        else:
            st.error("Invalid username or password.")

# Dashboard after login
if "logged_in" in st.session_state and st.session_state["logged_in"]:
    role = st.session_state["role"]
    username = st.session_state["username"]

    st.sidebar.write(f"Logged in as: {username} ({role})")

    # Recruiter Dashboard
    if role == "Recruiter":
        st.header("Recruiter Dashboard")
        st.subheader("Post a Job")
        
        job_title = st.text_input("Job Title")
        job_description = st.text_area("Job Description")
        
        if st.button("Post Job"):
            c.execute("INSERT INTO jobs (recruiter_id, job_title, job_description) VALUES (?, ?, ?)",
                      (st.session_state["user"][0], job_title, job_description))
            conn.commit()
            st.success("Job posted successfully!")
            # Notify all applicants
            c.execute("SELECT email FROM users WHERE role='Applicant'")
            applicants = c.fetchall()
            for applicant in applicants:
                send_email("New Job Posted", applicant[0], f"A new job '{job_title}' has been posted. Check it out!")

        st.subheader("Review Applications")
        c.execute("SELECT a.id, a.applicant_id, a.job_id, a.status, a.responses, a.assessment, u.email FROM applications a JOIN users u ON a.applicant_id = u.id WHERE a.job_id IN (SELECT id FROM jobs WHERE recruiter_id=?)", (st.session_state["user"][0],))
        applications = c.fetchall()

        for application in applications:
            app_id, applicant_id, job_id, status, responses, assessment, applicant_email = application
            st.write(f"**Application ID:** {app_id} | **Applicant Email:** {applicant_email} | **Status:** {status}")
            if st.button(f"Accept Application {app_id}"):
                c.execute("UPDATE applications SET status='Accepted' WHERE id=?", (app_id,))
                conn.commit()
                send_email("Application Status Update", applicant_email, "Congratulations! Your application has been accepted.")
                st.success(f"Application {app_id} accepted and email sent to {applicant_email}.")

            if st.button(f"Reject Application {app_id}"):
                rejection_reason = st.text_input("Reason for Rejection", key=f"reason_{app_id}")
                if rejection_reason and st.button("Submit Rejection"):
                    c.execute("UPDATE applications SET status='Rejected', rejection_reason=? WHERE id=?", (rejection_reason, app_id))
                    conn.commit()
                    send_email("Application Status Update", applicant_email, f"Your application has been rejected. Reason: {rejection_reason}")
                    st.success(f"Application {app_id} rejected and email sent to {applicant_email}.")

    # Applicant Dashboard
    elif role == "Applicant":
        st.header("Applicant Dashboard")
        st.subheader("Available Jobs")

        @st.cache_data
        def fetch_jobs():
            c.execute("SELECT * FROM jobs")
            return c.fetchall()

        jobs = fetch_jobs()
        for job in jobs:
            st.write(f"**{job[2]}** - {job[3]}")
            apply_button = st.button(f"Apply for {job[2]}", key=f"apply_{job[0]}")

            if apply_button:
                st.session_state["current_job_id"] = job[0]
                st.session_state["job_description"] = job[3]
                cv_file = st.file_uploader("Upload Your CV", type=["pdf", "docx"], key="cv_uploader")

                if cv_file:
                    # Extract text from CV
                    cv_text = extract_text_from_cv(cv_file)
                    if cv_text:  # Ensure cv_text is not None
                        st.session_state["cv_text"] = cv_text

                        # Generate a summary of the CV
                        cv_summary = generate_cv_summary(cv_text)
                        st.markdown("### CV Summary")
                        st.text(cv_summary)  # Display the CV summary

                        # Generate interview questions based on the CV summary and job description
                        generated_questions = generate_questionnaire(cv_summary, st.session_state["job_description"])
                        st.markdown("### Generated Interview Questions")
                        st.text(generated_questions)  # Display generated questions

                        # Allow applicant to input interview responses
                        interview_responses = st.text_area("Enter Your Interview Responses", height=300)

                        if st.button("Submit Responses"):
                            assessment_result = "Assessment Result Placeholder"  # Replace with actual assessment logic
                            st.success(f"Assessment Result: {assessment_result}")

                            # Save application record
                            c.execute("INSERT INTO applications (applicant_id, job_id, status, responses, assessment) VALUES (?, ?, ?, ?, ?)",
                                      (st.session_state["user"][0], st.session_state["current_job_id"], "Applied", interview_responses, assessment_result))
                            conn.commit()
                            st.success("Application submitted successfully!")

# Close the database connection when the app ends
conn.close()
