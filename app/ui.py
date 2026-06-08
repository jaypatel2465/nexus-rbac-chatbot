import streamlit as st
import requests
from requests.auth import HTTPBasicAuth
import base64
from pathlib import Path

API_URL = "http://localhost:8000"

# 1. Changed layout to "centered" to bring everything inward
st.set_page_config(page_title="NeXus Data Assistant", page_icon="🤖", layout="centered")

# -------------------------
# BACKGROUND IMAGES
# -------------------------
def set_bg_from_local(image_path):
    resolved_path = Path(__file__).resolve().parent.parent / image_path
    if not resolved_path.exists():
        return

    with open(resolved_path, "rb") as image_file:
        encoded = base64.b64encode(image_file.read()).decode()

    css = f"""
    <style>
    .stApp {{
        background-image: url("data:image/jpg;base64,{encoded}");
        background-size: cover;
        background-position: center;
        background-repeat: no-repeat;
        background-attachment: fixed;
    }}
    </style>
    """
    st.markdown(css, unsafe_allow_html=True)

set_bg_from_local("static/images/background4.jpg")

# -------------------------
# SESSION INIT
# -------------------------
if "auth" not in st.session_state:
    st.session_state.auth = None
if "role" not in st.session_state:
    st.session_state.role = None
if "page" not in st.session_state:
    st.session_state.page = "login"
if "username" not in st.session_state:
    st.session_state.username = ""
if "roles" not in st.session_state:
    st.session_state.roles = []

def fetch_roles():
    try:
        role_res = requests.get(
            f"{API_URL}/roles",
            auth=HTTPBasicAuth(*st.session_state.auth),
            timeout=10,
        )
        return role_res.json().get("roles", [])
    except Exception:
        return []

# -------------------------
# LOGIN PAGE
# -------------------------
if st.session_state.page == "login":
    # The Header Box
    st.markdown("""
    <div style="background-color: rgba(255, 255, 255, 0.85); 
        padding: 20px; border-radius: 5px; box-shadow: 0px 0px 10px gray;
        text-align: center; margin-bottom: 25px;">
        <h2>Welcome to NeXus</h2>
        <p>Your Document Assistant to get insights about the Company.</p>
    </div>
    """, unsafe_allow_html=True)

    
    username = st.text_input("Username")
    password = st.text_input("Password", type="password")

    if st.button("Login"):
        if not username.strip() or not password.strip():
            st.warning("Please enter both username and password.")
        else:
            try:
                res = requests.get(
                    f"{API_URL}/login",
                    auth=HTTPBasicAuth(username, password),
                    timeout=10,
                )
            except requests.exceptions.ConnectionError:
                st.error("Cannot connect to backend. Make sure the FastAPI server is running on port 8000.")
                res = None
            except requests.exceptions.Timeout:
                st.error("Backend request timed out. Please try again.")
                res = None
            except Exception as exc:
                st.error(f"Login request failed: {exc}")
                res = None

            if res and res.status_code == 200:
                st.session_state.auth = (username, password)
                st.session_state.username = username
                st.session_state.role = res.json()["role"]
                st.session_state.roles = fetch_roles()
                st.session_state.page = "main"
                st.rerun()
            elif res is not None:
                try:
                    st.error(res.json().get("detail", "Login failed."))
                except Exception:
                    st.error("Server error. Please check FastAPI logs.")

# -------------------------
# MAIN APP AFTER LOGIN 
# -------------------------
if st.session_state.page == "main":
    username = st.session_state.username
    role = st.session_state.role

    # Re-introducing columns only for the main app dashboard layout if desired
    left_col, right_col = st.columns([7, 2])

    with right_col:
        st.markdown(f"**👤 User:** `{username}`  \n**🛡️ Role:** `{role}`")
        if st.button("🚪 Logout"):
            st.session_state.auth = None
            st.session_state.role = None
            st.session_state.page = "login"
            st.rerun()
    
    with left_col:
        st.markdown("""
        <div style="background-color: rgba(255, 255, 255, 0.85); 
            padding: 10px; border-radius: 5px; box-shadow: 0px 0px 10px gray;
            text-align: center;">
            <h2>Welcome to NeXus</h2>
            <p>Your Document Assistant to get insights about the Company.</p>
        </div>
        """, unsafe_allow_html=True)
        
        st.markdown("")
        if role == "C-Level":
            st.write("You have global access")
            tab1, tab2, tab3 = st.tabs(["💬 Chat", "🧾 Upload (C-Level)", "👤 Admin (C-Level)"])
        elif role == "general":
            st.write(f"You have access to documents and features related to the `{role}` role.")
            (tab1,) = st.tabs(["💬 Chat"])
        else:
            st.write(f"You have access to documents and features related to the `{role}` role.")
            st.markdown("You also have access to **General documents**")
            (tab1,) = st.tabs(["💬 Chat"])
    
    # --- Chat Tab ---
    with tab1:
        st.subheader("Ask a question:")
        question = st.text_input("Your Question")
        if st.button("Submit"):
            res = requests.post(
                f"{API_URL}/chat",
                json={"question": question, "role": st.session_state.role},
                auth=HTTPBasicAuth(*st.session_state.auth)
            )
            
            if res.status_code == 200:
                st.success("✅ Answer Fetched Successfully:")
                
                # Custom CSS Box container for high visibility text
                answer_text = res.json()["answer"]
                
                st.markdown(f"""
                <div style="
                    background-color: rgba(255, 255, 255, 0.92); 
                    padding: 20px; 
                    border-radius: 8px; 
                    box-shadow: 0px 4px 12px rgba(0, 0, 0, 0.15);
                    color: #1E293B;
                    font-size: 16px;
                    line-height: 1.6;
                    margin-top: 15px;
                    border-left: 5px solid #2e7d32;
                ">
                    {answer_text}
                </div>
                """, unsafe_allow_html=True)
                
            else:
                st.error("❌ Something went wrong while processing your question.")
                
    # --- Upload & Admin Tabs (C-Level) ---
    if st.session_state.role == "C-Level":
        with tab2:
            st.subheader("Upload Documents")
            roles = st.session_state.roles
            selected_role = st.selectbox("Select document access role", roles)
            doc_file = st.file_uploader("Upload document (.md or .csv)", type=["csv", "md"])
            
            if st.button("Upload Document") and doc_file:
                try:
                    res = requests.post(
                        f"{API_URL}/upload-docs",
                        files={"file": doc_file},
                        data={"role": selected_role},
                        auth=HTTPBasicAuth(*st.session_state.auth),
                        timeout=120,
                    )
                    if res.ok:
                        st.success(res.json()["message"])
                    else:
                        st.error(res.json().get("detail", "Something went wrong."))
                except Exception as exc:
                    st.error(f"Upload failed: {exc}")

        with tab3:
            st.subheader("Add User")
            new_user = st.text_input("New Username")
            new_pass = st.text_input("New Password", type="password")
            new_role = st.selectbox("Assign Role", roles)
            if st.button("Create User"):
                try:
                    res = requests.post(
                        f"{API_URL}/create-user",
                        data={"username": new_user, "password": new_pass, "role": new_role},
                        auth=HTTPBasicAuth(*st.session_state.auth),
                        timeout=10,
                    )
                    if res.ok:
                        st.success(res.json()["message"])
                    else:
                        st.error(res.json().get("detail", "Something went wrong."))
                except Exception as exc:
                    st.error(f"Create user failed: {exc}")

            st.subheader("Create New Role")
            new_role_input = st.text_input("New Role Name")
            if st.button("Add Role"):
                try:
                    res = requests.post(
                        f"{API_URL}/create-role",
                        data={"role_name": new_role_input},
                        auth=HTTPBasicAuth(*st.session_state.auth),
                        timeout=10,
                    )
                    if res.ok:
                        st.success(res.json()["message"])
                        st.session_state.roles = fetch_roles()
                        st.rerun()
                    else:
                        st.error(res.json().get("detail", "Something went wrong."))
                except Exception as exc:
                    st.error(f"Create role failed: {exc}")
