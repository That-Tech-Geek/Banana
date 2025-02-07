import streamlit as st
import sqlite3
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import cohere
import hashlib
import datetime

# Initialize Cohere API
YOUR_COHERE_API_KEY= st.secrets["API"]
co = cohere.Client('YOUR_COHERE_API_KEY')

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

menu = ["Home", "Login", "Sign Up"]
choice = st.sidebar.selectbox("Menu", menu)

if choice == "Home":
    st.subheader("Welcome to Banana!")
    st.write("**The applicant-centric job search platform of the future.**")

elif choice == "Sign Up":
    st.subheader("Create an Account")
    username = st.text_input("Username")
    email = st.text_input("Email")  # New email field for notifications
    password = st.text_input("Password", type="password")
    role = st.radio("Register as:", ["Applicant", "Recruiter"])
    if st.button("Sign Up"):
        try:
            c.execute("INSERT INTO users (username, password, role) VALUES (?, ?, ?)", 
                      (username, hash_password(password), role))
            conn.commit()
            send_email("Welcome to Banana!", email, f"Hi {username},\n\nThank you for signing up as a {role}. Enjoy your job search journey!")
            st.success("Account created successfully! Go to Login.")
        except sqlite3.IntegrityError:
            st.error("Username already exists. Please choose a different one.")

elif choice == "Login":
    st.subheader("Login to Your Account")
    username = st.text_input("Username")
    password = st.text_input("Password", type="password")
    if st.button("Login"):
        user = authenticate_user(username, password)
        if user:
            st.session_state["logged_in"] = True
            st.session_state["user"] = user
            st.session_state["role"] = user[3]
            st.success(f"Welcome back, {username}!")
        else:
            st.error("Invalid username or password.")

# Logged-In Section
if "logged_in" in st.session_state and st.session_state["logged_in"]:
    role = st.session_state["role"]
    st.sidebar.write(f"Logged in as: {st.session_state['user'][1]} ({role})")

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
            
            # Send notification email to recruiter
            recruiter_email = "recruiter_email@example.com"  # Fetch this from the database in real usage
            send_email("Job Published Successfully", recruiter_email, f"Your job '{job_title}' has been published on Banana.")

    elif role == "Applicant":
        st.header("Applicant Dashboard")
        st.subheader("Available Jobs")
        
        c.execute("SELECT * FROM jobs")
        jobs = c.fetchall()
        for job in jobs:
            st.write(f"**{job[2]}** - {job[3]}")
            if st.button(f"Apply for {job[2]}", key=f"apply_{job[0]}"):
                c.execute("INSERT INTO applications (applicant_id, job_id) VALUES (?, ?)", 
                          (st.session_state["user"][0], job[0]))
                conn.commit()
                st.success(f"You have applied for '{job[2]}'!")

                # Send confirmation email to applicant
                applicant_email = "applicant_email@example.com"  # Fetch this from the database in real usage
                send_email("Job Application Confirmation", applicant_email, f"Hi {st.session_state['user'][1]},\n\nYou have successfully applied for '{job[2]}'. Good luck!")

        st.subheader("Your Applications")
        c.execute("SELECT jobs.job_title, jobs.job_description, applications.status FROM applications JOIN jobs ON applications.job_id = jobs.id WHERE applications.applicant_id=?", 
                  (st.session_state["user"][0],))
        applications = c.fetchall()
        for app in applications:
            st.write(f"**{app[0]}** - {app[1]} (Status: {app[2]})")
