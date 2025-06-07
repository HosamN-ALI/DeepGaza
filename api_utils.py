# api_utils.py
import requests
from openai import OpenAI
import streamlit as st
from db_utils import conn, get_cursor

def web_search(query, api_key):
    """Perform Google search and return formatted results."""
    headers = {"X-API-KEY": api_key, "Content-Type": "application/json"}
    payload = {
        "q": query,
        "gl": "us",
        "hl": "en",
        "num": 5  # Get top 5 results
    }

    try:
        response = requests.post(
            "https://google.serper.dev/search",
            headers=headers,
            json=payload,
            timeout=10
        )
        results = response.json()

        search_context = "\n".join([
            f"• [{item['title']}]({item['link']})\n  {item['snippet']}"
            for item in results.get("organic", [])[:3]  # Top 3 results
        ])
        return f"**Web Search Results**\n{search_context}\n\n"

    except Exception as e:
        st.error(f"Search failed: {str(e)}")
        return ""

def get_active_api_config():
    """Get the current active API configuration."""
    with get_cursor() as c: 
        c.execute("""
            SELECT base_url, api_key, model_name 
            FROM api_configurations 
            WHERE is_active = 1 
            LIMIT 1
        """)
        result = c.fetchone()
    return result or ("https://api.deepseek.com/v1", "", "deepseek-reasoner")

def process_stream(stream, used_key):
    """Process both reasoning and response phases, returning reasoning_content separately."""
    thinking_content = ""
    response_content = ""
    
    response_placeholder = st.empty()
    total_count = 0
    chunk_num = 0
    
    with st.status("Thinking...", expanded=True) as status:
        thinking_placeholder = st.empty()
        thinking_phase = True
        
        for chunk in stream:
            chunk_num += 1
            reasoning = getattr(chunk.choices[0].delta, "reasoning_content", "") or ""
            content = getattr(chunk.choices[0].delta, "content", "") or ""
            if thinking_phase:
                thinking_content += reasoning
                thinking_placeholder.markdown(thinking_content)
                if content:
                    status.update(label="Reasoning complete", state="complete", expanded=False)
                    thinking_phase = False
                    response_placeholder.markdown("▌")
            response_content += content
            if not thinking_phase:
                response_placeholder.markdown(response_content + "▌")
            adjusted_length = sum(2 if '\u4e00' <= c <= '\u9fff' else 1 for c in (reasoning + content))
            total_count += adjusted_length
            if chunk_num % 10 == 0:
                with get_cursor() as c: 
                    c.execute(
                        "UPDATE api_keys SET used_tokens = used_tokens + ? WHERE key = ?",
                        (total_count, used_key)
                    )
                    total_count = 0
        response_placeholder.markdown(response_content)
        with get_cursor() as c: 
            c.execute(
                "UPDATE api_keys SET used_tokens = used_tokens + ? WHERE key = ?",
                (total_count, used_key)
            )
    return thinking_content, response_content