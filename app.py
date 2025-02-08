import streamlit as st
import sqlite3
import pandas as pd
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os
import PyPDF2
import docx
import cohere
from werkzeug.security import generate_password_hash, check_password_hash

# Initialize Cohere API
cohere_client = cohere.Client('YOUR_COHERE_API_KEY')

# Database setup
def init_db():
    conn = sqlite3.connect('job_platform.db')
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY,
            email TEXT UNIQUE,
            password TEXT,
            role TEXT
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS jobs (
            id INTEGER PRIMARY KEY,
            title TEXT,
            description TEXT,
            recruiter_id INTEGER,
            FOREIGN KEY (recruiter_id) REFERENCES users (id)
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS applications (
            id INTEGER PRIMARY KEY,
            job_id INTEGER,
            applicant_id INTEGER,
            status TEXT,
            interview_response TEXT,
            FOREIGN KEY (job_id) REFERENCES jobs (id),
            FOREIGN KEY (applicant_id) REFERENCES users (id)
        )
    ''')
    conn.commit()
    conn.close()

# Email sending function
def send_email(to_email, subject, body):
    sender_email = st.secrets["email"]["username"]
    sender_password = st.secrets["email"]["password"]
    
    msg = MIMEMultipart()
    msg['From'] = sender_email
    msg['To'] = to_email
    msg['Subject'] = subject
    msg.attach(MIMEText(body, 'plain'))
    
    with smtplib.SMTP('smtp.gmail.com', 587) as server:
        server.starttls()
        server.login(sender_email, sender_password)
        server.send_message(msg)

# CV text extraction
def extract_text_from_cv(cv_file):
    if cv_file.type == "application/pdf":
        reader = PyPDF2.PdfReader(cv_file)
        text = ""
        for page in reader.pages:
            text += page.extract_text()
        return text
    elif cv_file.type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
        doc = docx.Document(cv_file)
        text = "\n".join([para.text for para in doc.paragraphs])
        return text
    return ""

# Cohere AI summary and questions generation
def generate_cv_summary_and_questions(cv_text, job_description):
    summary_response = cohere_client.summarize(text=cv_text)
    questions_response = cohere_client.generate(
        model='xlarge',
        prompt=f"Generate interview questions based on the following CV summary and job description:\n\nSummary: {summary_response.text}\nJob Description: {job_description}",
        max_tokens=100
    )
    return summary_response.text, questions_response.generations[0].text

# User authentication
def authenticate_user(email, password):
    conn = sqlite3.connect('job_platform.db')
    c = conn.cursor()
    c.execute('SELECT * FROM users WHERE email = ?', (email,))
    user = c.fetchone()
    conn.close()
    if user and check_password_hash(user[2], password):
        return user
    return None

# Streamlit app
def main():
    st.title("Job Platform Application")
    init_db()
    
    menu = ["Login", "Sign Up"]
    choice = st.sidebar.selectbox("Select an option", menu)

    if choice == "Sign Up":
        st.subheader("Create an Account")
        email = st.text_input("Email")
        password = st.text_input("Password", type='password')
        role = st.selectbox("Role", ["Applicant", "Recruiter"])
        
        if st.button("Sign Up"):
            hashed_password = generate_password_hash(password)
            conn = sqlite3.connect('job_platform.db')
            c = conn.cursor()
            try:
                c.execute('INSERT INTO users (email, password, role) VALUES (?, ?, ?)', (email, hashed_password, role))
                conn.commit()
                send_email(email, "Account Created", "Your account has been created successfully.")
                st.success("Account created! Please log in.")
            except sqlite3.IntegrityError:
                st.error("Email already exists.")
            conn.close()

    elif choice == "Login":
        st.subheader("Login to your account")
        email = st.text_input("Email")
        password = st.text_input("Password", type='password')
        
        if st.button("Login"):
            user = authenticate_user(email, password)
            if user:
                st.success(f"Welcome {user[3]}!")
                if user[3] == "Recruiter":
                    recruiter_dashboard(user[0])
                else:
                    applicant_dashboard(user[0])
            else:
                st.error("Invalid email or password.")

def recruiter_dashboard(recruiter_id):
    st.subheader("Recruiter Dashboard")
    job_title = st.text_input("Job Title")
    job_description = st.text_area("Job Description")
    
    if st.button("Post Job"):
        conn = sqlite3.connect('job_platform.db')
        c = conn.cursor()
        c.execute('INSERT INTO jobs (title, description, recruiter_id) VALUES (?, ?, ?)', (job_title, job_description, recruiter_id))
        conn.commit()
        send_email_to_applicants(job_title, job_description)
        st.success("Job posted successfully!")
        conn.close()

    st.subheader("Manage Applications")
    applications = get_applications_for_recruiter(recruiter_id)
    for app in applications:
        st.write(f"Application for {app[1]} by {app[2]} - Status: {app[3]}")
        if st.button(f"Accept {app[2]}"):
            update_application_status(app[0], "Accepted")
            send_email(app[2], "Application Status", "Your application has been accepted.")
            st.success("Application accepted.")
        if st.button(f"Reject {app[2]}"):
            update_application_status(app[0], "Rejected")
            send_email(app[2], "Application Status", "Your application has been rejected.")
            st.success("Application rejected.")

def applicant_dashboard(applicant_id):
    st.subheader("Applicant Dashboard")
    st.write("Available Jobs")
    jobs = get_available_jobs()
    for job in jobs:
        st.write(f"{job[1]} - {job[2]}")
        if st.button(f"Apply for {job[1]}"):
            cv_file = st.file_uploader("Upload your CV", type=["pdf", "docx"])
            if cv_file:
                cv_text = extract_text_from_cv(cv_file)
                summary, questions = generate_cv_summary_and_questions(cv_text, job[2])
                conn = sqlite3.connect('job_platform.db')
                c = conn.cursor()
                c.execute('INSERT INTO applications (job_id, applicant_id, status) VALUES (?, ?, ?)', (job[0], applicant_id, "Pending"))
                conn.commit()
                send_email(job[3], "New Application", f"You have a new application for {job[1]} from {applicant_id}.")
                st.success("Application submitted successfully!")
                st.write("CV Summary:", summary)
                st.write("Generated Interview Questions:", questions)
                conn.close()

def get_applications_for_recruiter(recruiter_id):
    conn = sqlite3.connect('job_platform.db')
    c = conn.cursor()
    c.execute('''
        SELECT applications.id, jobs.title, users.email, applications.status
        FROM applications
        JOIN jobs ON applications.job_id = jobs.id
        JOIN users ON applications.applicant_id = users.id
        WHERE jobs.recruiter_id = ?
    ''', (recruiter_id,))
    applications = c.fetchall()
    conn.close()
    return applications

def get_available_jobs():
    conn = sqlite3.connect('job_platform.db')
    c = conn.cursor()
    c.execute('SELECT id, title, description, recruiter_id FROM jobs')
    jobs = c.fetchall()
    conn.close()
    return jobs

def update_application_status(application_id, status):
    conn = sqlite3.connect('job_platform.db')
    c = conn.cursor()
    c.execute('UPDATE applications SET status = ? WHERE id = ?', (status, application_id))
    conn.commit()
    conn.close()

def send_email_to_applicants(job_title, job_description):
    conn = sqlite3.connect('job_platform.db')
    c = conn.cursor()
    c.execute('SELECT email FROM users WHERE role = "Applicant"')
    applicants = c.fetchall()
    for applicant in applicants:
        send_email(applicant[0], "New Job Posting", f"A new job has been posted: {job_title}\nDescription: {job_description}")
    conn.close()

if __name__ == "__main__":
    main() ```python
# Additional functionalities can be added here, such as user profile management, job search filters, and application history.

# User profile management
def user_profile(user_id):
    conn = sqlite3.connect('job_platform.db')
    c = conn.cursor()
    c.execute('SELECT email, role FROM users WHERE id = ?', (user_id,))
    user = c.fetchone()
    conn.close()
    
    st.subheader("User  Profile")
    st.write(f"Email: {user[0]}")
    st.write(f"Role: {user[1]}")
    
    if st.button("Update Email"):
        new_email = st.text_input("New Email")
        if new_email:
            conn = sqlite3.connect('job_platform.db')
            c = conn.cursor()
            c.execute('UPDATE users SET email = ? WHERE id = ?', (new_email, user_id))
            conn.commit()
            conn.close()
            st.success("Email updated successfully!")

# Job search filters
def job_search():
    st.subheader("Search for Jobs")
    search_term = st.text_input("Search by job title or description")
    if st.button("Search"):
        jobs = search_jobs(search_term)
        for job in jobs:
            st.write(f"{job[1]} - {job[2]}")

def search_jobs(search_term):
    conn = sqlite3.connect('job_platform.db')
    c = conn.cursor()
    c.execute('SELECT id, title, description FROM jobs WHERE title LIKE ? OR description LIKE ?', (f'%{search_term}%', f'%{search_term}%'))
    jobs = c.fetchall()
    conn.close()
    return jobs

# Application history for applicants
def application_history(applicant_id):
    st.subheader("Application History")
    applications = get_applications_for_applicant(applicant_id)
    for app in applications:
        st.write(f"Applied for {app[1]} - Status: {app[3]}")

def get_applications_for_applicant(applicant_id):
    conn = sqlite3.connect('job_platform.db')
    c = conn.cursor()
    c.execute('''
        SELECT jobs.title, applications.status
        FROM applications
        JOIN jobs ON applications.job_id = jobs.id
        WHERE applications.applicant_id = ?
    ''', (applicant_id,))
    applications = c.fetchall()
    conn.close()
    return applications

# Integrate the new functionalities into the applicant dashboard
def applicant_dashboard(applicant_id):
    st.subheader("Applicant Dashboard")
    job_search()
    application_history(applicant_id)
    st.write("Available Jobs")
    jobs = get_available_jobs()
    for job in jobs:
        st.write(f"{job[1]} - {job[2]}")
        if st.button(f"Apply for {job[1]}"):
            cv_file = st.file_uploader("Upload your CV", type=["pdf", "docx"])
            if cv_file:
                cv_text = extract_text_from_cv(cv_file)
                summary, questions = generate_cv_summary_and_questions(cv_text, job[2])
                conn = sqlite3.connect('job_platform.db')
                c = conn.cursor()
                c.execute('INSERT INTO applications (job_id, applicant_id, status) VALUES (?, ?, ?)', (job[0], applicant_id, "Pending"))
                conn.commit()
                send_email(job[3], "New Application", f"You have a new application for {job[1]} from {applicant_id}.")
                st.success("Application submitted successfully!")
                st.write("CV Summary:", summary)
                st.write("Generated Interview Questions:", questions)
                conn.close()
