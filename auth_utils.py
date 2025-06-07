# auth_utils.py
import bcrypt
import sqlite3
import streamlit as st
from db_utils import conn, get_cursor

def hash_password(password):
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

def verify_password(password, hashed):
    return bcrypt.checkpw(password.encode(), hashed.encode())

def is_blacklisted(username):
    with get_cursor() as c:
        c.execute('SELECT 1 FROM blacklist WHERE username = ?', (username,))
        return c.fetchone() is not None

def authenticate_user(username, password):
    with get_cursor() as c: 
        c.execute('SELECT password_hash, is_admin FROM users WHERE username = ?', (username,))
        result = c.fetchone()
    if result and verify_password(password, result[0]):
        st.session_state.is_admin = bool(result[1])
        return True
    return False

def login_form():
    with st.form("Login"):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        if st.form_submit_button("Login"):
            if is_blacklisted(username):
                st.error("Username is blacklisted")
                return
            elif authenticate_user(username, password):
                st.session_state.logged_in = True
                st.session_state.username = username
                st.rerun()
            else:
                st.error("Invalid credentials")

def register_form():
    with st.form("Register"):
        username = st.text_input("New username")
        password = st.text_input("New password", type="password")
        if st.form_submit_button("Register"):
            if is_blacklisted(username):
                st.error("Username is blacklisted")
                return
            try:
                with get_cursor() as c: 
                    c.execute('INSERT INTO users (username, password_hash) VALUES (?, ?)',
                         (username, hash_password(password)))
                st.success("Registration successful! Please log in.")
            except sqlite3.IntegrityError:
                st.error("Username already exists")