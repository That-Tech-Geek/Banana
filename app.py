import sqlite3
import hashlib
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import docx
from PyPDF2 import PdfReader
import cohere
import streamlit as st

# Cohere API setup
cohere_api_key = st.secrets["API"]  
try:
    co = cohere.Client(cohere_api_key)
except Exception as e:
    st.error(f"Error initializing Cohere API: {e}")
    co = None

# Email Settings
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
    """Extract text from uploaded CV file (PDF or DOCX)"""
    if cv_file.type == "application/pdf":
        pdf_reader = PdfReader(cv_file)
        text = "".join(page.extract_text() for page in pdf_reader.pages)
        return text
    elif cv_file.type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
        doc = docx.Document(cv_file)
        text = "\n".join(para.text for para in doc.paragraphs)
        return text
    else:
        return "Unsupported file type"

def generate_cv_summary(cv_text):
    """Generate a summary for the uploaded CV using Cohere"""
    if co is None:
        return "Cohere API is not available."
    
    prompt = f"Summarize the following CV text into a concise and informative summary:\n\n{cv_text}\n\nSummary:"
    try:
        response = co.generate(
            model="command",
            prompt=prompt,
            max_tokens=300,
            temperature=0.7
        )
        if response and hasattr(response, 'generations') and response.generations:
            return response.generations[0].text.strip()
        else:
            return "No summary generated. Please check the input."
    except Exception as e:
        st.error(f"Error generating CV summary: {e}")
        return "Error generating summary."

def generate_interview_questions(summary, job_description):
    """Generate interview questions based on CV summary and job description"""
    if co is None:
        return "Cohere API is not available."
    
    prompt = f"Based on the following job description and applicant's summary, generate 15 relevant interview questions:\n\nJob Description: {job_description}\n\nApplicant Summary: {summary}\n\nInterview Questions:"
    try:
        response = co.generate(
            model="command",
            prompt=prompt,
            max_tokens=1000,
            temperature=0.7
        )
        if response and hasattr(response, 'generations') and response.generations:
            return response.generations[0].text.strip()
        else:
            return "No questions generated. Please check the input."
    except Exception as e:
        st.error(f"Error generating interview questions: {e}")
        return "Error generating interview questions."

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

# Streamlit App
st.title("🍌 Banana: Ultimate Job Search Platform")

menu = ["Home", "Login", "Sign Up"]
choice = st.sidebar.selectbox("Menu", menu)

if choice == "Home":
    st.subheader("Welcome to Banana!")
    st.write("**The applicant-centric job search platform of the future.**")

elif choice == "Sign Up":
    st.subheader("Create an Account")
    email = st.text_input("Email")
    password = st.text_input("Password", type="password")
    role = st.radio("Register as:", ["Applicant", "Recruiter"])
    
    if st.button("Sign Up"):
        try:
            c.execute("SELECT * FROM users WHERE email=? AND role=?", (email, role))
            if c.fetchone():
                st.error(f"An account already exists for {role} with this email.")
            else:
                username = st.text_input(f"{role} Username")
                c.execute("INSERT INTO users (username, email, password, role) VALUES (?, ?, ?, ?)",
                          (username, email, hash_password(password), role))
                conn.commit()
                send_email("Job Application Confirmation", email, f"Hi {username},\n\nWelcome to Banana!")
                st.success("Account created successfully!")
        except sqlite3.IntegrityError:
            st.error("Username already exists. Try a different one.")

elif choice == "Login":
    st.subheader("Login to Your Account")
    username = st.text_input("Username")
    password = st.text_input("Password", type="password")
    if st.button("Login"):
        user = authenticate_user(username, password)
        if user:
            st.session_state["logged_in"] = True
            st.session_state["user"] = user
            st.success(f"Welcome back, {username}!")
            
            # Application Submission Section
            st.subheader("Submit Your Application")
            job_id = st.selectbox("Select Job", [job[1] for job in c.execute("SELECT id, job_title FROM jobs").fetchall()])
            cv_file = st.file_uploader("Upload your CV (PDF or DOCX)", type=["pdf", "docx"])
            
            if st.button("Submit Application"):
                if cv_file is not None:
                    cv_text = extract_text_from_cv(cv_file)
                    summary = generate_cv_summary(cv_text)
                    job_description = c.execute("SELECT job_description FROM jobs WHERE id=?", (job_id,)).fetchone()[0]
                    interview_questions = generate_interview_questions(summary, job_description)
                    
                    # Save application to the database
                    c.execute("INSERT INTO applications (applicant_id, job_id, responses) VALUES (?, ?, ?)",
                              (user[0], job_id, summary))
                    conn.commit()
                    st.success("Application submitted successfully!")
                    st.write("Generated Interview Questions:")
                    st.write(interview_questions)
                else:
                    st.error("Please upload your CV before submitting the application.")
        else:
            st.error("Invalid username or password.")
