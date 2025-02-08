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

# Utility Functions (unchanged)
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
            # Check if the email already exists for the chosen role
            c.execute("SELECT * FROM users WHERE email=? AND role=?", (email, role))
            existing_user = c.fetchone()
            if existing_user:
                st.error(f"An account already exists for {role} with this email. Please login or use a different email.")
            else:
                # Register the user
                username = st.text_input(f"{role} Username")
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
            # Storing session data after login
            st.session_state["logged_in"] = True
            st.session_state["user"] = user  # Storing entire user data
            st.session_state["role"] = user[4]
            st.session_state["username"] = user[1]  # Storing username
            st.success(f"Welcome back, {username}!")
        else:
            st.error("Invalid username or password.")

# Dashboard after login
if "logged_in" in st.session_state and st.session_state["logged_in"]:
    role = st.session_state["role"]
    username = st.session_state["username"]

    st.sidebar.write(f"Logged in as: {username} ({role})")

    # Applicant Dashboard
    if role == "Applicant":
        st.header("Applicant Dashboard")
        st.subheader("Available Jobs")

        # Fetching jobs from the database
        @st.cache_data
        def fetch_jobs():
            c.execute("SELECT * FROM jobs")
            return c.fetchall()

        jobs = fetch_jobs()
        for job in jobs:
            st.write(f"**{job[2]}** - {job[3]}")
            apply_button = st.button(f"Apply for {job[2]}", key=f"apply_{job[0]}")

            if apply_button:
                # Storing the job ID and description in session state
                st.session_state["current_job_id"] = job[0]
                st.session_state["job_description"] = job[3]
                cv_file = st.file_uploader("Upload Your CV", type=["pdf", "docx"])

                if cv_file:
                    cv_text = extract_text_from_cv(cv_file)
                    st.session_state["cv_text"] = cv_text
                    st.session_state["cv_summary"] = generate_cv_summary(cv_text)

                    # Generate Interview Questions
                    interview_questions = generate_interview_questions(st.session_state["cv_summary"], st.session_state["job_description"])
                    st.markdown("### Interview Questions")
                    st.text(interview_questions)  # Display questions as static text

                    # Allow applicant to input interview responses
                    interview_responses = st.text_area("Enter Your Interview Responses", height=300)

                    if st.button("Submit Responses"):
                        st.session_state["responses"] = interview_responses  # Store responses in session state
                        assessment_result = assess_application(cv_text, st.session_state["job_description"], interview_responses.split("\n"))
                        st.success(f"Assessment Result: {assessment_result}")

                        # Save application record
                        c.execute("INSERT INTO applications (applicant_id, job_id, status, responses, assessment) VALUES (?, ?, ?, ?, ?)",
                                  (st.session_state["user"][0], st.session_state["current_job_id"], "Applied", interview_responses, assessment_result))
                        conn.commit()
