import streamlit as st
import sqlite3
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import cohere
import hashlib
import datetime

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
    username = st.text_input("Username")
    email = st.text_input("Email")
    password = st.text_input("Password", type="password")
    role = st.radio("Register as:", ["Applicant", "Recruiter"])
    if st.button("Sign Up"):
        try:
            c.execute("INSERT INTO users (username, email, password, role) VALUES (?, ?, ?, ?)",
                      (username, email, hash_password(password), role))
            conn.commit()
            send_email("Welcome to Banana!", email, f"Hi {username},\n\nThank you for signing up as a {role}. Enjoy your job search journey!")
            st.success("Account created successfully! Go to Login.")
        except sqlite3.IntegrityError:
            st.error("Username or email already exists. Please choose a different one.")

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
            st.success(f"Welcome back, {username}!")
        else:
            st.error("Invalid username or password.")

# Dashboard After Login
if "logged_in" in st.session_state and st.session_state["logged_in"]:
    role = st.session_state["role"]
    st.sidebar.write(f"Logged in as: {st.session_state['user'][1]} ({role})")

    # Recruiter Dashboard
    if role == "Recruiter":
        st.header("Recruiter Dashboard")
        job_title = st.text_input("Job Title")
        job_description = st.text_area("Job Description")
        
        if st.button("Publish Job"):
            interview_questions = "Sample interview questions generated here."  # Placeholder for Cohere output
            c.execute("INSERT INTO jobs (recruiter_id, job_title, job_description, interview_questions) VALUES (?, ?, ?, ?)",
                      (st.session_state["user"][0], job_title, job_description, interview_questions))
            conn.commit()
            st.success(f"Job '{job_title}' has been published!")
            send_email("Job Published Successfully", st.session_state["user"][2], f"Your job '{job_title}' has been published on Banana.")

    # Applicant Dashboard
    elif role == "Applicant":
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
                c.execute("INSERT INTO applications (applicant_id, job_id) VALUES (?, ?)",
                          (st.session_state["user"][0], job[0]))
                conn.commit()
                st.success(f"You have applied for '{job[2]}'!")
                send_email("Job Application Confirmation", st.session_state["user"][2],
                           f"Hi {st.session_state['user'][1]},\n\nYou have successfully applied for '{job[2]}'. Good luck!")

        st.subheader("Your Applications")
        c.execute("""SELECT jobs.job_title, jobs.job_description, applications.status 
                     FROM applications 
                     JOIN jobs ON applications.job_id = jobs.id 
                     WHERE applications.applicant_id=?""", (st.session_state["user"][0],))
        applications = c.fetchall()
        for app in applications:
            st.write(f"**{app[0]}** - {app[1]} (Status: {app[2]})")
