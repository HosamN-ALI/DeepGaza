# helper_utils.py
import json
import uuid
from datetime import datetime
import streamlit as st
from db_utils import conn, get_cursor

def save_session():
    """保存当前会话到数据库"""
    if st.session_state.get("valid_key") and "current_session_id" in st.session_state:
        try:
            session_data = json.dumps(st.session_state.messages)
            with get_cursor() as c: 
                username = c.execute(
                    "SELECT username FROM api_keys WHERE key = ?",
                    (st.session_state.used_key,)
                ).fetchone()[0]
                
                c.execute("""
                    INSERT INTO history (
                        username, 
                        session_id, 
                        session_name, 
                        session_data
                    ) VALUES (?, ?, ?, ?)
                    ON CONFLICT(session_id) DO UPDATE SET
                        session_data = excluded.session_data,
                        updated_at = CURRENT_TIMESTAMP
                """, (
                    username,
                    st.session_state.current_session_id,
                    f"会话-{datetime.now().strftime('%m-%d %H:%M')}",
                    session_data
                ))

                # 清理旧记录
                c.execute("""
                    DELETE FROM history 
                    WHERE username = ?
                    AND id NOT IN (
                        SELECT id 
                        FROM history 
                        WHERE username = ?
                        ORDER BY updated_at DESC 
                        LIMIT 10
                    )
                """, (username, username))

        except Exception as e:
            st.error(f"保存会话失败: {str(e)}")

def load_session(session_id):
    """从数据库加载指定会话"""
    try:
        with get_cursor() as c: 
            c.execute("""
                SELECT session_data 
                FROM history 
                WHERE session_id = ?
            """, (session_id,))
            if data := c.fetchone():
                st.session_state.messages = json.loads(data[0])
                st.session_state.current_session_id = session_id
                st.rerun()
    except Exception as e:
        st.error(f"加载会话失败: {str(e)}")

def display_message(message):
    """显示聊天消息"""
    role = message["role"]
    with st.chat_message(role):
        if role == "assistant":
            _display_assistant_message(message["content"])
        else:
            st.markdown(message["content"])

def _display_assistant_message(content):
    """解析并显示助理消息"""
    if "<think>" in content:
        parts = content.split("</think>")
        with st.expander("查看思考过程"):
            st.markdown(f"```\n{parts[0][7:]}\n```")
        st.markdown(parts[1])
    else:
        st.markdown(content)

def display_chat_history():
    """显示完整的聊天记录"""
    for message in st.session_state.messages:
        if message["role"] != "system":
            display_message(message)
