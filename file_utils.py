# file_utils.py
import hashlib
import os
import textract
import streamlit as st

def save_uploaded_files(upload_dir, uploaded_files):
    """Save uploaded files to a temporary directory and return file info."""
    saved_files = []
    current_files = [f["name"] for f in st.session_state.get("uploaded_files", [])]

    for file in uploaded_files:
        if file.name in current_files:
            continue

        if file.size > 10 * 1024 * 1024:  # 10MB limit
            st.error(f"File {file.name} exceeds size limit.")
            continue

        try:
            # Save file to specified directory
            file_path = os.path.join(upload_dir, file.name)
            with open(file_path, "wb") as f:
                f.write(file.getbuffer())

            # Parse file content
            if file.name.endswith(('.doc', '.docx', '.pdf', '.jpg', '.png')):
                content = textract.process(file_path).decode("utf-8")
            else:
                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read()

            # Generate content hash
            content_hash = hashlib.md5(content.encode()).hexdigest()

            # Check for duplicate content
            if any(f["hash"] == content_hash for f in st.session_state.uploaded_files):
                continue

            saved_files.append({
                "name": file.name,
                "content": content,
                "size": file.size,
                "hash": content_hash
            })

        except Exception as e:
            st.error(f"Failed to parse file {file.name}: {str(e)}")
            continue

    return saved_files

def format_file_contents(files):
    """Format file contents as a string with separators."""
    return "\n".join([f"=== {f['name']} ===\n{f['content']}\n" for f in files])