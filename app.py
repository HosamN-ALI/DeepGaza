import base64
import re
import streamlit as st
import uuid
import os
from dotenv import load_dotenv
from openai import OpenAI
from db_utils import conn, get_cursor
from auth_utils import login_form, register_form, hash_password
from admin_utils import admin_panel, setup_admin
from file_utils import save_uploaded_files, format_file_contents
from api_utils import web_search, get_active_api_config, process_stream
from helper_utils import save_session, load_session, display_chat_history

# ====== Hide Streamlit branding, deploy banner, and logo ======
hide_streamlit_style = """
    <style>
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: visible;}
    .stDeployButton {display: none !important;}
    .st-emotion-cache-1wbqy5l, .st-emotion-cache-1eyfjps, .st-emotion-cache-usvq0g, .stAppDeployButton, .st-emotion-cache-1w7bu1y {
        display: none !important;
    }
    .st-emotion-cache-1p1m4ay, .st-emotion-cache-83erdr, .st-emotion-cache-1f3w014, .st-emotion-cache-usvq0g {
        display: none !important;
    }
    [data-testid="stAppDeployButton"] {display: none !important;}
    </style>
"""
st.markdown(hide_streamlit_style, unsafe_allow_html=True)
# =============================================================

# Default system role template
DEFAULT_SYSTEM_ROLE = (
    "You are an AI assistant, please answer the questions asked by the user. "
    "At the same time, if the user provides search results, please add the corresponding references in the answer. "
    "If you need to output mathematical formulas in LaTeX format, please write mathematical formulas in Obsidian compatible LaTeX format, "
    "with the following requirements: 1. Inline formulas are wrapped with a single $, such as $x^2$. "
    "2. Independent formula blocks are wrapped with two $$, such as: $$\\int_a^b f(x)dx$$."
)

def handle_user_input():
    base_url = "https://api.deepseek.com/v1"
    api_key = os.getenv("DEEPSEEK_API_KEY")
    model_name = "deepseek-reasoner"
    
    if not api_key:
        st.error("API key not found. Please check your .env file.")
        return
        
    client = OpenAI(api_key=api_key, base_url=base_url)

    uploaded_files = st.file_uploader(
        "Upload text files (supports multiple)",
        type=["txt", "docx", "doc", 'pdf', 'jpg', 'png'],
        accept_multiple_files=True,
        key="file_uploader"
    )

    if uploaded_files:
        new_files = save_uploaded_files(dirs, uploaded_files)
        st.session_state.uploaded_files.extend(new_files)
        st.session_state['file_uploader'].clear()

    user_content = []
    if user_input := st.chat_input("Ask me anything!"):
        user_content.append(user_input)

        if st.session_state.get('enable_search', False):
            try:
                search_results = web_search(user_input, search_key)
                user_content.insert(0, search_results)
            except Exception as e:
                st.error(f"Search failed: {str(e)}")

        if st.session_state.uploaded_files:
            file_content = format_file_contents(st.session_state.uploaded_files)
            user_content.append("\n[Uploaded files content]\n" + file_content)
            st.session_state.uploaded_files = []

        full_content = "\n".join(user_content)

        with get_cursor() as c:
            key_obj = c.execute('SELECT id, key, used_tokens, total_tokens FROM api_keys WHERE key = ?', 
                        (api_key,)).fetchone()
        adjusted_length = sum(2 if '\u4e00' <= c <= '\u9fff' else 1 for c in full_content)
        if key_obj and key_obj[2] + adjusted_length >= key_obj[3]:
            st.error("Quota exhausted, please contact the admin.")
            return

        with get_cursor() as c:
            c.execute('UPDATE api_keys SET used_tokens = used_tokens + ? WHERE key = ?', 
                 (adjusted_length, api_key))

        st.session_state.messages.append({"role": "user", "content": full_content})
        with st.chat_message("user"):
            st.markdown(user_input)

        with st.chat_message("assistant"):
            stream = client.chat.completions.create(
                model=model_name,
                messages=st.session_state.messages,
                stream=True,
                max_tokens=32768
            )
            reasoning_content, total_content = process_stream(stream, api_key)
            st.session_state.messages.append(
                {"role": "assistant", "content": total_content}
            )
            if reasoning_content:
                st.markdown("**Reasoning Chain:**")
                st.info(reasoning_content)
        save_session()

def main_interface():
    st.title("DeepGaza Chat")

    if "uploaded_files" not in st.session_state:
        st.session_state.uploaded_files = []

    with st.sidebar:
        st.markdown("<h2 style='text-align:center;'>DeepGaza</h2>", unsafe_allow_html=True)
        if st.button("⚙️ - Settings"):
            st.session_state.show_admin = not st.session_state.get('show_admin', False)

        st.session_state.enable_search = st.checkbox(
            "🔍 Enable web search",
            value=st.session_state.get('enable_search', False),
            help="When enabled, information will be fetched from the web"
        )

        # System Role input (optional)
        system_role_input = st.text_area(
            "Add System Role (optional)",
            value=st.session_state.get("custom_system_role", ""),
            placeholder="Add System Role (optional)",
            key="system_role_input"
        )

        # Store the value for later use
        st.session_state.custom_system_role = system_role_input.strip()

        if st.session_state.get('valid_key'):
            username = "admin"
            if st.button("🆕 - New Chat"):
                st.session_state.current_session_id = str(uuid.uuid4())
                # Determine which system role to use
                system_content = st.session_state.custom_system_role.strip()
                if system_content:
                    system_message = {
                        "role": "system",
                        "content": (
                            f"{system_content}, please answer the questions asked by the user. "
                            "At the same time, if the user provides search results, please add the corresponding references in the answer. "
                            "If you need to output mathematical formulas in LaTeX format, please write mathematical formulas in Obsidian compatible LaTeX format, "
                            "with the following requirements: 1. Inline formulas are wrapped with a single $, such as $x^2$. "
                            "2. Independent formula blocks are wrapped with two $$, such as: $$\\int_a^b f(x)dx$$."
                        )
                    }
                else:
                    system_message = {"role": "system", "content": DEFAULT_SYSTEM_ROLE}
                st.session_state.messages = [system_message]
                st.session_state.show_admin = False
                st.rerun()

            st.subheader("Chat History")
            with get_cursor() as c:
                histories = c.execute('''
                    SELECT session_id, session_name, updated_at 
                    FROM history 
                    WHERE username = ? 
                    ORDER BY updated_at DESC 
                    LIMIT 10
                ''', (username,)).fetchall()

            for hist in histories:
                session_id = hist[0]
                current_name = hist[1]
                
                col1, col2, col3 = st.columns([4, 1, 1])
                
                with col1:
                    if st.session_state.get('editing_session') == session_id:
                        new_name = st.text_input(
                            "Edit name",
                            value=current_name,
                            key=f"edit_{session_id}",
                            label_visibility="collapsed"
                        )
                    else:
                        if st.button(
                            f"🗨️ {current_name}",
                            key=f"load_{session_id}",
                            help="Click to load the conversation"
                        ):
                            st.session_state.show_admin = False
                            load_session(session_id)
                
                with col2:
                    if st.session_state.get('editing_session') == session_id:
                        if st.button(
                            "💾",
                            key=f"save_{session_id}",
                            help="Save changes",
                            type="primary"
                        ):
                            if new_name.strip():
                                with get_cursor() as c:
                                    c.execute(
                                        'UPDATE history SET session_name = ? WHERE session_id = ?',
                                        (new_name.strip(), session_id)
                                    )
                            del st.session_state.editing_session
                            st.rerun()
                    else:
                        if st.button(
                            "✏️",
                            key=f"edit_{session_id}",
                            help="Edit name"
                        ):
                            st.session_state.editing_session = session_id
                            st.rerun()
                
                with col3:
                    if st.button(
                        "×",
                        key=f"del_{session_id}",
                        help="Delete conversation"
                    ):
                        with get_cursor() as c:
                            c.execute('DELETE FROM history WHERE session_id = ?', (session_id,))
                        if st.session_state.get('editing_session') == session_id:
                            del st.session_state.editing_session
                        st.rerun()

    if st.session_state.get('show_admin'):
        admin_panel()
    else:
        display_chat_history()
        handle_user_input()

def main():
    setup_admin(admin_user, hash_password(admin_pass), api_key)

    if 'current_session_id' not in st.session_state:
        st.session_state.current_session_id = str(uuid.uuid4())

    if "messages" not in st.session_state:
        # Determine which system role to use at startup
        system_content = st.session_state.get("custom_system_role", "").strip()
        if system_content:
            system_message = {
                "role": "system",
                "content": (
                    f"{system_content}, please answer the questions asked by the user. "
                    "At the same time, if the user provides search results, please add the corresponding references in the answer. "
                    "If you need to output mathematical formulas in LaTeX format, please write mathematical formulas in Obsidian compatible LaTeX format, "
                    "with the following requirements: 1. Inline formulas are wrapped with a single $, such as $x^2$. "
                    "2. Independent formula blocks are wrapped with two $$, such as: $$\\int_a^b f(x)dx$$."
                )
            }
        else:
            system_message = {"role": "system", "content": DEFAULT_SYSTEM_ROLE}
        st.session_state.messages = [system_message]
        st.session_state.valid_key = False

    if not st.session_state.get('valid_key'):
        user_key = st.chat_input("Add System Role (optional)")
        # If the user enters a value in the API key/system role field, use it as the system role!
        if user_key:
            st.session_state.custom_system_role = user_key.strip()
            st.session_state.valid_key = True
            st.session_state.used_key = os.getenv("DEEPSEEK_API_KEY")
            st.session_state.username = "admin"
            # Replace system message with the customized one
            st.session_state.messages = [{
                "role": "system",
                "content": (
                    f"{user_key.strip()}, please answer the questions asked by the user. "
                    "At the same time, if the user provides search results, please add the corresponding references in the answer. "
                    "If you need to output mathematical formulas in LaTeX format, please write mathematical formulas in Obsidian compatible LaTeX format, "
                    "with the following requirements: 1. Inline formulas are wrapped with a single $, such as $x^2$. "
                    "2. Independent formula blocks are wrapped with two $$, such as: $$\\int_a^b f(x)dx$$."
                )
            }]
            st.rerun()
        else:
            # If left blank, use the default
            st.session_state.custom_system_role = ""
            st.session_state.valid_key = True
            st.session_state.used_key = os.getenv("DEEPSEEK_API_KEY")
            st.session_state.username = "admin"
            st.session_state.messages = [{
                "role": "system",
                "content": DEFAULT_SYSTEM_ROLE
            }]
            st.rerun()

    main_interface()

if __name__ == "__main__":
    load_dotenv()

    dirs = 'uploads/'
    admin_user = os.getenv("ADMIN_USERNAME") 
    admin_pass = os.getenv("ADMIN_PASSWORD") 
    api_key = os.getenv("DEEPSEEK_API_KEY")
    search_key = os.getenv("SEARCH_API_KEY") 
    model_name = "deepseek-reasoner"

    if not os.path.exists(dirs):
        os.makedirs(dirs)

    main()