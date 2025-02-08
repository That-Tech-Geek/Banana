import streamlit as st
import sqlite3
import smtplib
import cohere
import hashlib
from email.mime.text import MIMEText
from PyPDF2 import PdfReader
from docx import Document
from io import BytesIO
import os
import datetime

# ---------------------------
# Helper Functions & DB Setup
# ---------------------------
def init_db():
    conn = sqlite3.connect("job_platform.db")
    c = conn.cursor()
    
    # Ensure the users table exists before attempting to alter it
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            email TEXT UNIQUE,
            password TEXT,
            role TEXT
        )
    ''')
    
    # Check if 'name' column exists before adding it
    c.execute("PRAGMA table_info(users)")
    columns = [col[1] for col in c.fetchall()]
    if "name" not in columns:
        c.execute("ALTER TABLE users ADD COLUMN name TEXT;")
    
    # Jobs table: includes job details
    c.execute('''
        CREATE TABLE IF NOT EXISTS jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT,
            description TEXT,
            location TEXT,
            salary INTEGER,
            remote BOOLEAN
        )
    ''')
    
    # Applications table: stores job applications by applicants
    c.execute('''
        CREATE TABLE IF NOT EXISTS applications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id INTEGER,
            applicant_id INTEGER,
            cv_text TEXT,
            status TEXT,
            applied_on DATETIME
        )
    ''')
    
    # Referrals table (optional additional feature)
    c.execute('''
        CREATE TABLE IF NOT EXISTS referrals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            referrer_id INTEGER,
            referred_email TEXT,
            status TEXT
        )
    ''')
    
    conn.commit()
    conn.close()
    
def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def send_email(subject, body, recipient):
    try:
        sender_email = os.getenv("EMAIL")
        sender_password = os.getenv("EMAIL_PASSWORD")
        msg = MIMEText(body)
        msg["Subject"] = subject
        msg["From"] = sender_email
        msg["To"] = recipient

        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()
            server.login(sender_email, sender_password)
            server.sendmail(sender_email, recipient, msg.as_string())
    except Exception as e:
        st.error(f"Email sending failed: {e}")

def extract_text_from_file(uploaded_file):
    if uploaded_file is None:
        return ""
    if uploaded_file.type == "application/pdf":
        try:
            reader = PdfReader(uploaded_file)
            return " ".join([page.extract_text() for page in reader.pages if page.extract_text()])
        except Exception as e:
            st.error(f"Error reading PDF: {e}")
            return ""
    elif uploaded_file.type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
        try:
            doc = Document(uploaded_file)
            return " ".join([para.text for para in doc.paragraphs])
        except Exception as e:
            st.error(f"Error reading DOCX: {e}")
            return ""
    return ""

def summarize_cv(cv_text):
    try:
        co = cohere.Client(os.getenv("COHERE_API_KEY"))
        response = co.summarize(text=cv_text, length="short")
        return response.summary
    except Exception as e:
        st.error(f"Error summarizing CV: {e}")
        return cv_text[:200]  # fallback: first 200 characters

def generate_interview_questions(cv_summary, job_desc):
    try:
        co = cohere.Client(os.getenv("COHERE_API_KEY"))
        prompt = f"Based on this CV summary: {cv_summary} and job description: {job_desc}, generate relevant interview questions."
        response = co.generate(prompt=prompt, max_tokens=100)
        return response.generations[0].text.strip()
    except Exception as e:
        st.error(f"Error generating interview questions: {e}")
        return "What makes you a good fit for this role?"

# ---------------------------
# Authentication Pages
# ---------------------------
def login_page():
    """Handles user login for the job platform."""
    st.title("Login")

    email = st.text_input("Email")
    password = st.text_input("Password", type="password")

    if st.button("Login"):
        if not email or not password:
            st.error("⚠️ Please enter both email and password.")
            return

        hashed_password = hash_password(password)

        try:
            conn = sqlite3.connect("job_platform.db")
            c = conn.cursor()

            # Ensure the `users` table exists
            c.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT,
                    email TEXT UNIQUE,
                    password TEXT,
                    role TEXT
                )
            ''')
            conn.commit()

            # Fetch user details
            c.execute("SELECT id, name, email, role FROM users WHERE email = ? AND password = ?", 
                      (email, hashed_password))
            user = c.fetchone()
            conn.close()

            if user:
                st.session_state.user = {
                    "id": user[0],
                    "name": user[1],
                    "email": user[2],
                    "role": user[3]
                }
                st.success(f"✅ Welcome back, {user[1]}!")
                st.rerun()  # Updated from experimental_rerun()
            else:
                st.error("❌ Invalid email or password. Please try again.")

        except sqlite3.Error as e:
            st.error(f"⚠️ Database error: {e}")

def signup_page():
    st.title("Sign Up")
    name = st.text_input("Name")
    email = st.text_input("Email")
    password = st.text_input("Password", type="password")
    role = st.selectbox("Role", ["Applicant", "Recruiter"])
    if st.button("Sign Up"):
        conn = sqlite3.connect("job_platform.db")
        c = conn.cursor()
        hashed = hash_password(password)
        try:
            c.execute("INSERT INTO users (name, email, password, role) VALUES (?, ?, ?, ?)", (name, email, hashed, role))
            conn.commit()
            send_email("Welcome to Job Platform", f"Hello {name}, your account has been created successfully!", email)
            st.success("Account created! Please login.")
        except sqlite3.IntegrityError:
            st.error("Email already exists.")
        conn.close()

def logout():
    if "user" in st.session_state:
        del st.session_state.user
    st.rerun()

# ---------------------------
# Applicant Pages & Dashboard
# ---------------------------
def applicant_job_listings():
    st.subheader("Job Listings")
    conn = sqlite3.connect("job_platform.db")
    c = conn.cursor()
    # Advanced search filters
    title_filter = st.text_input("Job Title")
    location_filter = st.text_input("Location")
    remote_filter = st.selectbox("Remote Option", ["Any", "Yes", "No"])
    salary_min = st.number_input("Minimum Salary", value=0)
    salary_max = st.number_input("Maximum Salary", value=1000000)
    
    # Only show jobs posted by recruiter accounts
    query = """
    SELECT jobs.id, jobs.title, jobs.description, jobs.location, jobs.salary, jobs.remote, jobs.recruiter_id
    FROM jobs
    JOIN users ON jobs.recruiter_id = users.id
    WHERE users.role = 'Recruiter'
    """
    params = []
    if title_filter:
        query += " AND jobs.title LIKE ?"
        params.append(f"%{title_filter}%")
    if location_filter:
        query += " AND jobs.location LIKE ?"
        params.append(f"%{location_filter}%")
    if remote_filter != "Any":
        query += " AND jobs.remote = ?"
        params.append(1 if remote_filter == "Yes" else 0)
    query += " AND jobs.salary BETWEEN ? AND ?"
    params.append(salary_min)
    params.append(salary_max)
    
    c.execute(query, params)
    jobs = c.fetchall()
    for job in jobs:
        st.markdown(f"### {job[1]}")
        st.write(job[2])
        st.write(f"Location: {job[3]} | Salary: {job[4]} | Remote: {'Yes' if job[5] else 'No'}")
        if st.button(f"Apply for {job[1]}", key=f"apply_{job[0]}"):
            st.session_state.selected_job = job
            st.rerun()
    conn.close()

def applicant_apply_page():
    job = st.session_state.get("selected_job", None)
    if not job:
        st.error("No job selected.")
        return
    st.subheader(f"Apply for {job[1]}")
    st.write(job[2])
    uploaded_file = st.file_uploader("Upload your CV (PDF/DOCX)", type=["pdf", "docx"])
    if st.button("Submit Application"):
        if uploaded_file is None:
            st.error("Please upload your CV.")
            return
        cv_text = extract_text_from_file(uploaded_file)
        cv_summary = summarize_cv(cv_text)
        interview_questions = generate_interview_questions(cv_summary, job[2])
        conn = sqlite3.connect("job_platform.db")
        c = conn.cursor()
        c.execute("INSERT INTO applications (job_id, applicant_id, cv_text, status, applied_on) VALUES (?, ?, ?, ?, ?)",
                  (job[0], st.session_state.user['id'], cv_text, "Pending", datetime.datetime.now()))
        conn.commit()
        conn.close()
        send_email("Application Received",
                   f"Your application for {job[1]} has been submitted.\n\nInterview Questions:\n{interview_questions}",
                   st.session_state.user['email'])
        st.success("Application Submitted Successfully!")
        if "selected_job" in st.session_state:
            del st.session_state.selected_job
        st.rerun()
    st.write("---")
    st.subheader("Interview Preparation")
    st.write(generate_interview_questions(summarize_cv("dummy"), job[2]))  # demo question if none generated

def applicant_applications():
    st.subheader("My Applications")
    conn = sqlite3.connect("job_platform.db")
    c = conn.cursor()
    c.execute(
        "SELECT a.id, j.title, a.status, a.applied_on FROM applications a JOIN jobs j ON a.job_id = j.id WHERE a.applicant_id = ?",
        (st.session_state.user['id'],))
    apps = c.fetchall()
    for app in apps:
        st.write(f"Application ID: {app[0]} | Job: {app[1]} | Status: {app[2]} | Applied On: {app[3]}")
    conn.close()

def resume_builder():
    st.subheader("Resume Builder")
    name = st.text_input("Name", value=st.session_state.user.get('name', ''))
    education = st.text_area("Education")
    experience = st.text_area("Experience")
    skills = st.text_area("Skills")
    if st.button("Generate Resume"):
        resume_text = f"Name: {name}\n\nEducation:\n{education}\n\nExperience:\n{experience}\n\nSkills:\n{skills}"
        st.text_area("Your Resume", value=resume_text, height=300)

def interview_simulation():
    st.subheader("Interview Simulation")
    sample_question = "Can you describe a challenging situation at work and how you handled it?"
    st.write(f"**Interview Question:** {sample_question}")
    response = st.text_area("Your Answer")
    if st.button("Submit Answer"):
        try:
            co = cohere.Client(os.getenv("COHERE_API_KEY"))
            prompt = f"Provide constructive feedback for the following answer: {response}"
            feedback_response = co.generate(prompt=prompt, max_tokens=50)
            feedback = feedback_response.generations[0].text.strip()
        except Exception as e:
            feedback = "Feedback generation failed."
        st.write(f"**Feedback:** {feedback}")

def career_chatbot():
    st.subheader("Career Guidance Chatbot")
    user_input = st.text_input("Ask a career-related question")
    if st.button("Get Advice"):
        try:
            co = cohere.Client(os.getenv("COHERE_API_KEY"))
            prompt = f"You are a career guidance expert. Answer the following question: {user_input}"
            response = co.generate(prompt=prompt, max_tokens=100)
            advice = response.generations[0].text.strip()
        except Exception as e:
            advice = "Sorry, I couldn't generate advice at this time."
        st.write(advice)

def applicant_dashboard():
    menu = st.sidebar.radio("Navigation", 
                            ["Job Listings", "Apply for Job", "My Applications", 
                             "Resume Builder", "Interview Simulation", "Career Chatbot", "Logout"])
    if menu == "Job Listings":
        applicant_job_listings()
    elif menu == "Apply for Job":
        applicant_apply_page()
    elif menu == "My Applications":
        applicant_applications()
    elif menu == "Resume Builder":
        resume_builder()
    elif menu == "Interview Simulation":
        interview_simulation()
    elif menu == "Career Chatbot":
        career_chatbot()
    elif menu == "Logout":
        logout()

# ---------------------------
# Recruiter Pages & Dashboard
# ---------------------------
def recruiter_post_job():
    st.subheader("Post a New Job")
    title = st.text_input("Job Title")
    description = st.text_area("Job Description")
    location = st.text_input("Location")
    salary = st.number_input("Salary", value=0)
    remote = st.selectbox("Remote", ["Yes", "No"]) == "Yes"
    if st.button("Post Job"):
        try:
            conn = sqlite3.connect("job_platform.db")
            c = conn.cursor()
            # Convert the boolean 'remote' to an integer (1 for True, 0 for False)
            c.execute(
                "INSERT INTO jobs (title, description, location, salary, remote, recruiter_id) VALUES (?, ?, ?, ?, ?, ?)",
                (title, description, location, salary, int(remote), st.session_state.user['id'])
            )
            conn.commit()
            conn.close()
            st.success("Job Posted Successfully!")
        except Exception as e:
            st.error(f"Error posting job: {e}")

def recruiter_view_jobs():
    st.subheader("Your Posted Jobs")
    conn = sqlite3.connect("job_platform.db")
    c = conn.cursor()
    c.execute("SELECT * FROM jobs WHERE recruiter_id = ?", (st.session_state.user['id'],))
    jobs = c.fetchall()
    for job in jobs:
        st.markdown(f"### {job[1]}")
        st.write(job[2])
        st.write(f"Location: {job[3]} | Salary: {job[4]} | Remote: {'Yes' if job[5] else 'No'}")
    conn.close()

def recruiter_manage_applications():
    st.subheader("Manage Applications")
    conn = sqlite3.connect("job_platform.db")
    c = conn.cursor()
    # Fetch jobs posted by this recruiter
    c.execute("SELECT id, title FROM jobs WHERE recruiter_id = ?", (st.session_state.user['id'],))
    jobs = c.fetchall()
    for job in jobs:
        st.markdown(f"#### Applications for {job[1]}")
        c.execute("SELECT a.id, u.name, u.email, a.status FROM applications a JOIN users u ON a.applicant_id = u.id WHERE a.job_id = ?", (job[0],))
        apps = c.fetchall()
        for app in apps:
            st.write(f"Application ID: {app[0]} | Applicant: {app[1]} | Email: {app[2]} | Status: {app[3]}")
            col1, col2 = st.columns(2)
            with col1:
                if st.button(f"Accept {app[0]}", key=f"accept_{app[0]}"):
                    c.execute("UPDATE applications SET status = ? WHERE id = ?", ("Accepted", app[0]))
                    conn.commit()
                    send_email("Application Update",
                               f"Your application for {job[1]} has been accepted.",
                               app[2])
                    st.success("Application Accepted")
            with col2:
                if st.button(f"Reject {app[0]}", key=f"reject_{app[0]}"):
                    c.execute("UPDATE applications SET status = ? WHERE id = ?", ("Rejected", app[0]))
                    conn.commit()
                    send_email("Application Update",
                               f"Your application for {job[1]} has been rejected.",
                               app[2])
                    st.error("Application Rejected")
    conn.close()

def recruiter_analytics():
    st.subheader("Application Analytics")
    conn = sqlite3.connect("job_platform.db")
    c = conn.cursor()
    c.execute("SELECT status, COUNT(*) FROM applications GROUP BY status")
    data = c.fetchall()
    statuses = [row[0] for row in data]
    counts = [row[1] for row in data]
    st.bar_chart(data=counts)
    for status, count in data:
        st.write(f"{status}: {count}")
    conn.close()

def recruiter_dashboard():
    menu = st.sidebar.radio("Navigation", 
                            ["Post Job", "View Posted Jobs", "Manage Applications", "Analytics", "Logout"])
    if menu == "Post Job":
        recruiter_post_job()
    elif menu == "View Posted Jobs":
        recruiter_view_jobs()
    elif menu == "Manage Applications":
        recruiter_manage_applications()
    elif menu == "Analytics":
        recruiter_analytics()
    elif menu == "Logout":
        logout()

# ---------------------------
# Main App
# ---------------------------
def main():
    st.set_page_config(page_title="AI-Powered Job Platform", layout="wide")
    init_db()
    if "user" not in st.session_state:
        auth_mode = st.sidebar.selectbox("Choose Option", ["Login", "Sign Up"])
        if auth_mode == "Login":
            login_page()
        else:
            signup_page()
    else:
        st.sidebar.write(f"Logged in as {st.session_state.user['name']} ({st.session_state.user['role']})")
        if st.session_state.user['role'] == "Applicant":
            applicant_dashboard()
        else:
            recruiter_dashboard()

if __name__ == "__main__":
    main()
