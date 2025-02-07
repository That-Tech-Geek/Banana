import streamlit as st
import sqlite3
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import cohere
import hashlib
import datetime
from PyPDF2 import PdfReader
import docx

# Initialize Cohere API
YOUR_COHERE_API_KEY = st.secrets["API"]
co = cohere.Client(YOUR_COHERE_API_KEY)

# Email Configuration
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
EMAIL_ADDRESS = st.secrets["EMAIL-ADDRESS"]
EMAIL_PASSWORD = st.secrets["EMAIL-PASSWORD"]

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

# Generate Interview Questions using Cohere
def generate_interview_questions(cv_text, job_description):
    prompt = f"Based on the following job description and applicant's CV, generate 15 relevant interview questions:\n\nJob Description: {job_description}\n\nCV: {cv_text}\n\nInterview Questions. Generate only the questions, and no other text AT ALL."
    response = co.generate(
        model="command",
        prompt=prompt,
        max_tokens=20000,
        temperature=0.7
    )
    
    # Check if response has choices and extract the generated text correctly
    if response and hasattr(response, 'generations') and response.generations:
        return response.generations[0].text.strip()  # Extract text from the first generation
    else:
        return "No questions generated, please check the input data."

# Streamlit App
st.title("🍌 Banana: Ultimate Job Search Platform")

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
                    send_email("Welcome to Banana!", email, f"Hi {username},\n\nThank you for signing up as a {role}. Enjoy your job search journey!")
                    st.success(f"Account created successfully as a {role}! Go to Login.")
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

        @st.cache(allow_output_mutation=True)
        def fetch_jobs():
            c.execute("SELECT * FROM jobs")
            return c.fetchall()

        jobs = fetch_jobs()
        for job in jobs:
            st.write(f"**{job[2]}** - {job[3]}")
            if st.button(f"Apply for {job[2]}", key=f"apply_{job[0]}"):
                # Store the job ID in the session state
                st.session_state["current_job_id"] = job[0]
                st.session_state["job_description"] = job[3]
                st.session_state["show_form"] = True

        if "show_form" in st.session_state and st.session_state["show_form"]:
            # CV upload form
            st.subheader("Upload Your CV")
            cv_file = st.file_uploader("Choose your CV (PDF or Word)", type=["pdf", "docx"])

            if cv_file:
                # Extract text from the uploaded CV
                cv_text = extract_text_from_cv(cv_file)
                job_description = st.session_state["job_description"]
                
                # Generate interview questions based on CV and job description
                interview_questions = generate_interview_questions(cv_text, job_description)
                st.write("### Generated Interview Questions:")
                st.write(interview_questions)

                # Store the questions in session state to show on the form
                st.session_state["interview_questions"] = interview_questions.split("\n")
                
                # Ask questions and collect responses
                responses = []
                for question in st.session_state["interview_questions"]:
                    response = st.text_input(f"Question: {question}")
                    responses.append(response)

                if st.button("Submit Application"):
                    # Save the responses to the database
                    responses_str = "\n".join(responses)
                    c.execute("INSERT INTO applications (applicant_id, job_id, responses) VALUES (?, ?, ?)",
                              (st.session_state["user"][0], st.session_state["current_job_id"], responses_str))
                    conn.commit()
                    st.success("You have successfully applied for the job!")
                    st.session_state["show_form"] = False  # Reset form visibility

                    # Send confirmation email to applicant
                    send_email("Job Application Confirmation", st.session_state["user"][2],
                               f"Hi {st.session_state['user'][1]},\n\nYou have successfully applied for the job '{job[2]}'. Good luck!"
