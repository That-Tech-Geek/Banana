import streamlit as st
import sqlite3
import smtplib
import cohere
import hashlib
from email.mime.text import MIMEText
from PyPDF2 import PdfReader
from docx import Document
from io import BytesIO
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
    conn.commit()
    
    # Check if 'name' column exists in users; add it if missing
    c.execute("PRAGMA table_info(users)")
    user_columns = [col[1] for col in c.fetchall()]
    if "name" not in user_columns:
        c.execute("ALTER TABLE users ADD COLUMN name TEXT;")
    conn.commit()
    
    # Create the jobs table if it doesn't exist with all required columns
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
    conn.commit()
    
    # Check if required columns exist in jobs table; add any missing ones.
    c.execute("PRAGMA table_info(jobs)")
    jobs_columns = [col[1] for col in c.fetchall()]
    if "location" not in jobs_columns:
        c.execute("ALTER TABLE jobs ADD COLUMN location TEXT;")
    if "salary" not in jobs_columns:
        c.execute("ALTER TABLE jobs ADD COLUMN salary INTEGER;")
    if "remote" not in jobs_columns:
        c.execute("ALTER TABLE jobs ADD COLUMN remote BOOLEAN;")
    conn.commit()
    
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
        sender_email = st.secrets["EMAIL-ADDRESS"]
        sender_password = st.secrets["EMAIL_PASSWORD"]
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
        co = cohere.Client(st.secrets["API"])
        response = co.summarize(text=cv_text, length="short")
        return response.summary
    except Exception as e:
        st.error(f"Error summarizing CV: {e}")
        return cv_text[:200]  # fallback: first 200 characters

def generate_interview_questions(cv_summary, job_desc):
    try:
        co = cohere.Client(st.secrets["COHERE_API_KEY"])
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
    uploaded_cv = st.file_uploader("Upload CV", type=["pdf", "docx"])
    if uploaded_cv:
        cv_text = extract_text_from_file(uploaded_cv)
        if cv_text:
            cv_summary = summarize_cv(cv_text)
            st.text_area("CV Summary", value=cv_summary, height=150)
            job_description = job[2]
            interview_questions = generate_interview_questions(cv_summary, job_description)
            st.write("Suggested Interview Questions:")
            st.write(interview_questions)

            if st.button("Submit Application"):
                conn = sqlite3.connect("job_platform.db")
                c = conn.cursor()
                c.execute("INSERT INTO applications (job_id, applicant_id, cv_text, status, applied_on) VALUES (?, ?, ?, ?, ?)", 
                          (job[0], st.session_state.user["id"], cv_text, "Pending", datetime.datetime.now()))
                conn.commit()
                conn.close()
                st.success("Application Submitted!")
                st.session_state.selected_job = None
                st.rerun()

# ---------------------------
# Main Streamlit Application
# ---------------------------
def main():
    init_db()

    # Handle user sessions
    if "user" not in st.session_state:
        st.sidebar.title("Job Platform")
        option = st.sidebar.selectbox("Select an action", ["Login", "Sign Up"])

        if option == "Login":
            login_page()
        elif option == "Sign Up":
            signup_page()
    else:
        st.sidebar.title("Welcome!")
        st.sidebar.write(f"Logged in as: {st.session_state.user['name']}")
        st.sidebar.write(f"Role: {st.session_state.user['role']}")
        if st.sidebar.button("Logout"):
            logout()

        # Applicant Dashboard
        if st.session_state.user["role"] == "Applicant":
            applicant_job_listings()
            if "selected_job" in st.session_state:
                applicant_apply_page()

# ---------------------------
# Run the app
# ---------------------------
if __name__ == "__main__":
    main()
