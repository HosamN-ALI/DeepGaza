# admin_utils.py
import streamlit as st
from db_utils import conn, get_cursor
from auth_utils import hash_password, login_form, register_form
import sqlite3
import os

def update_admin_status(user_id, is_admin):
    with get_cursor() as c:
        c.execute('UPDATE users SET is_admin = ? WHERE id = ?', (int(is_admin), user_id))

def delete_user(user_id):
    with get_cursor() as c:
        c.execute('SELECT username FROM users WHERE id = ?', (user_id,))
        row = c.fetchone()
        if row:
            c.execute('DELETE FROM api_keys WHERE username = ?', (row[0],))
        c.execute('DELETE FROM users WHERE id = ?', (user_id,))

def setup_admin(admin_user, admin_pass, key):
    with get_cursor() as c:
        c.execute('SELECT 1 FROM users WHERE username = ?', (admin_user,))
        if not c.fetchone():
            c.execute('''
                INSERT INTO users (username, password_hash, is_admin)
                VALUES (?, ?, 1)
                ON CONFLICT(username)
                DO UPDATE SET
                    password_hash = excluded.password_hash,
                    is_admin = excluded.is_admin
            ''', (admin_user, admin_pass))
        c.execute('SELECT 1 FROM api_configurations WHERE config_name = ?', ("default",))
        if not c.fetchone():
            c.execute('''
                INSERT INTO api_configurations (config_name, base_url, api_key, model_name, is_active)
                VALUES (?, ?, ?, ?, 1)
            ''', ("default",
                "https://api.deepseek.com/v1",
                key,
                "deepseek-reasoner"))

def admin_panel():
    if not st.session_state.get('logged_in'):
        login_form()
        return

    if not st.session_state.is_admin:
        st.header("User Panel")
        with get_cursor() as c:
            keys = c.execute('''SELECT id, key, username, used_tokens, total_tokens
                            FROM api_keys WHERE is_active = 1 AND username = ?''',
                        (st.session_state.username,)).fetchall()
            for key in keys:
                with st.expander(f"Key {key[0]}"):
                    st.write(f"Key: {key[1]}")
                    st.write(f"Username: {key[2]}")
                    st.write(f"Used tokens: {key[3]}")
                    st.write(f"Total tokens: {key[4]}")
        return

    st.header("DeepGaza Admin Panel")  # Changed header
    tab1, tab2, tab3, tab4 = st.tabs(["API Key Info", "API Configurations", "Users", "Blacklist"])

    with tab1:
        st.subheader("API Key(s)")
        st.info("API Key is set by the system administrator in the environment file (.env) only. Users cannot create or modify API keys from the interface.")
        with get_cursor() as c:
            keys = c.execute('SELECT id, key, username, used_tokens, total_tokens FROM api_keys WHERE is_active = 1').fetchall()
            for key in keys:
                with st.expander(f"Key {key[1]}"):
                    st.write(f"Key: {key[1]}")
                    st.write(f"User: {key[2]}")
                    st.write(f"Used tokens: {key[3]}")
                    st.write(f"Total tokens: {key[4]}")

    with tab2:
        st.subheader("API Configuration Management")
        st.info("API configuration is managed by the system. To change the API key, edit the .env file and restart the application.")
        with get_cursor() as c:
            configs = c.execute('SELECT id, config_name, base_url, model_name, is_active FROM api_configurations').fetchall()
            for config in configs:
                with st.expander(f"{config[1]} ({'Active' if config[4] else 'Inactive'})"):
                    st.code(f"Base URL: {config[2]}\nModel: {config[3]}")

    with tab3:
        st.subheader("User Management")
        register_form()
        with get_cursor() as c:
            users = c.execute('SELECT id, username, is_admin FROM users').fetchall()
        for user in users:
            cols = st.columns([3,1,1])
            cols[0].write(user[1])
            is_admin = cols[1].checkbox("Admin", value=bool(user[2]), key=f"admin_{user[1]}")
            if is_admin != user[2]:
                update_admin_status(user[0], is_admin)
            if cols[2].button("Delete", key=f"del_{user[1]}"):
                delete_user(user[0])
                st.rerun()

    with tab4:
        st.subheader("Blacklist Management")
        with get_cursor() as c:
            with st.form("Blacklist Actions"):
                username = st.text_input("Username")
                reason = st.text_input("Reason")
                col1, col2 = st.columns(2)
                if col1.form_submit_button("Add"):
                    try:
                        c.execute('INSERT INTO blacklist (username, reason) VALUES (?, ?)', (username, reason))
                        st.success("Added to blacklist")
                    except sqlite3.IntegrityError:
                        st.error("User already in blacklist")
                if col2.form_submit_button("Remove"):
                    c.execute('DELETE FROM blacklist WHERE username = ?', (username,))
                    st.success("Removed from blacklist")

            st.subheader("Blacklist Entries")
            blacklist = c.execute('SELECT username, reason FROM blacklist').fetchall()
            for entry in blacklist:
                st.write(f"{entry[0]} - {entry[1]}")