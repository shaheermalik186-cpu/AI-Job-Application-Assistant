from __future__ import annotations

import os
from datetime import date
from io import BytesIO
from urllib.parse import quote_plus

import pandas as pd
import streamlit as st

from modules.cover_letter import generate_cover_letter
from modules.database import SupabaseStore, SupabaseSetupError
from modules.gemini_service import GeminiService, GeminiSetupError
from modules.job_matcher import match_job
from modules.job_search import search_adzuna, search_links
from modules.resume_parser import ResumeParseError, extract_resume_text, profile_from_text

st.set_page_config(page_title="AI Job Application Assistant", page_icon="🎯", layout="wide")

MAX_UPLOAD_MB = 5


def get_secret(name: str, default: str = "") -> str:
    try:
        value = st.secrets.get(name, default)
    except Exception:
        value = default
    return str(value or os.getenv(name, default))


def init_state() -> None:
    defaults = {
        "resume_text": "", "resume_name": "", "profile": None,
        "job_results": [], "selected_job": None, "cover_letter": "",
        "auth_user": None, "auth_store": None, "supabase_client": None,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def get_ai() -> GeminiService | None:
    key = get_secret("GEMINI_API_KEY")
    if not key:
        return None
    return GeminiService(api_key=key, model=get_secret("GEMINI_MODEL", "gemini-flash-latest"))


def get_store() -> SupabaseStore | None:
    url, key = get_secret("SUPABASE_URL"), get_secret("SUPABASE_ANON_KEY")
    if not url or not key:
        return None
    return SupabaseStore(url=url, anon_key=key)


def profile_summary(profile: dict) -> None:
    c1, c2, c3 = st.columns(3)
    c1.metric("Skills found", len(profile.get("skills", [])))
    c2.metric("Experience", f"{profile.get('experience_years', 0)} years")
    c3.metric("Target roles", len(profile.get("target_roles", [])))
    st.write("**Skills:** " + (", ".join(profile.get("skills", [])) or "Not detected"))
    st.write("**Education:** " + (", ".join(profile.get("education", [])) or "Not detected"))
    st.write("**Suggested roles:** " + (", ".join(profile.get("target_roles", [])) or "Add a target role below"))


def render_auth(store: SupabaseStore | None) -> bool:
    st.sidebar.subheader("Account")
    if store is None:
        st.sidebar.warning("Supabase is not configured. Add SUPABASE_URL and SUPABASE_ANON_KEY to use persistent, account-based tracking.")
        st.sidebar.caption("Without Supabase, the tracker works only in this browser session.")
        return False

    if st.session_state.auth_user:
        user = st.session_state.auth_user
        st.sidebar.success(f"Signed in: {user.get('email', 'account')}")
        if st.sidebar.button("Sign out"):
            try:
                store.sign_out()
            except Exception:
                pass
            st.session_state.auth_user = None
            st.session_state.auth_store = None
            st.session_state.supabase_client = None
            st.rerun()
        return True

    tab_signin, tab_signup = st.sidebar.tabs(["Sign in", "Create account"])
    with tab_signin:
        with st.form("sign_in_form"):
            email = st.text_input("Email", key="login_email")
            password = st.text_input("Password", type="password", key="login_password")
            submitted = st.form_submit_button("Sign in", use_container_width=True)
        if submitted:
            try:
                user = store.sign_in(email.strip(), password)
                st.session_state.auth_user = user
                st.session_state.auth_store = store
                st.session_state.supabase_client = store.client
                st.rerun()
            except Exception as exc:
                st.error(f"Sign-in failed: {exc}")
    with tab_signup:
        with st.form("sign_up_form"):
            new_email = st.text_input("Email address", key="signup_email")
            new_password = st.text_input("Password (at least 8 characters)", type="password", key="signup_password")
            submitted_signup = st.form_submit_button("Create account", use_container_width=True)
        if submitted_signup:
            try:
                result = store.sign_up(new_email.strip(), new_password)
                if result.get("id"):
                    st.success("Account created. If email confirmation is enabled in Supabase, verify your email before signing in.")
                else:
                    st.info("Check your email for a confirmation link, then sign in.")
            except Exception as exc:
                st.error(f"Account creation failed: {exc}")
    return False


def get_current_store(store: SupabaseStore | None) -> SupabaseStore | None:
    if store and st.session_state.auth_user:
        return st.session_state.auth_store or store
    return None


def render_resume_tab(ai: GeminiService | None) -> None:
    st.header("1. Resume profile")
    st.write("Upload your resume to extract skills and experience. Your resume is kept in app memory for analysis and is not automatically saved to the database.")
    uploaded = st.file_uploader("Upload resume", type=["pdf", "docx", "txt"], help=f"Maximum {MAX_UPLOAD_MB} MB")
    if uploaded:
        if uploaded.size > MAX_UPLOAD_MB * 1024 * 1024:
            st.error(f"Please upload a file smaller than {MAX_UPLOAD_MB} MB.")
        elif st.button("Parse resume", type="primary"):
            try:
                text = extract_resume_text(uploaded.name, uploaded.getvalue())
                if len(text.strip()) < 40:
                    st.error("Not enough text could be extracted. If this is a scanned PDF, run OCR first or upload a text-based PDF/DOCX.")
                else:
                    st.session_state.resume_text = text[:30000]
                    st.session_state.resume_name = uploaded.name
                    with st.spinner("Extracting profile..."):
                        if ai:
                            profile = ai.extract_profile(st.session_state.resume_text)
                        else:
                            profile = profile_from_text(st.session_state.resume_text)
                    st.session_state.profile = profile
                    st.success("Resume profile is ready.")
            except ResumeParseError as exc:
                st.error(str(exc))
            except Exception as exc:
                st.error(f"Could not parse the resume: {exc}")

    if st.session_state.profile:
        profile_summary(st.session_state.profile)
        st.caption("Please review extracted details. AI extraction can miss information; edit target roles and location below.")
        st.session_state.profile["target_roles"] = st.multiselect(
            "Target roles", options=list(dict.fromkeys(st.session_state.profile.get("target_roles", []) + ["Data Analyst", "Software Engineer", "Python Developer", "AI Engineer", "Business Analyst", "Marketing Executive"])),
            default=st.session_state.profile.get("target_roles", []),
        )
        st.session_state.profile["preferred_location"] = st.text_input(
            "Preferred Pakistan location", value=st.session_state.profile.get("preferred_location", "Pakistan")
        )
        st.session_state.profile["experience_years"] = st.number_input(
            "Years of experience (approx.)", min_value=0, max_value=50,
            value=int(st.session_state.profile.get("experience_years", 0) or 0), step=1,
        )


def render_jobs_tab(ai: GeminiService | None) -> None:
    st.header("2. Find and match jobs")
    st.info("Pakistan job listings depend on the configured provider's coverage. If live API coverage is unavailable, use the search links or paste a job description to analyze it.")
    profile = st.session_state.profile or {}
    c1, c2 = st.columns(2)
    with c1:
        query = st.text_input("Job title / keywords", value=(profile.get("target_roles") or [""])[0])
        location = st.text_input("City in Pakistan", value=profile.get("preferred_location", "Pakistan"))
    with c2:
        job_type = st.selectbox("Work preference", ["Any", "On-site", "Hybrid", "Remote"])
        experience = st.selectbox("Experience level", ["Any", "Entry level", "Junior", "Mid-level", "Senior"])
    if st.button("Search jobs", type="primary"):
        if not query.strip():
            st.warning("Enter a job title or keyword first.")
        else:
            jobs = []
            adzuna_id = get_secret("ADZUNA_APP_ID")
            adzuna_key = get_secret("ADZUNA_APP_KEY")
            if adzuna_id and adzuna_key:
                with st.spinner("Checking configured job provider..."):
                    try:
                        jobs = search_adzuna(query, location, adzuna_id, adzuna_key, country="pk")
                    except Exception as exc:
                        st.warning(f"Live provider could not return results: {exc}")
            st.session_state.job_results = jobs
            st.session_state.search_links = search_links(query, location, job_type, experience)
            if not jobs:
                st.info("No API listings returned. Use the Pakistan job search links below or add a job description manually.")

    for link in st.session_state.get("search_links", []):
        st.markdown(f"- [{link['label']}]({link['url']})")

    jobs = st.session_state.get("job_results", [])
    if jobs:
        for idx, job in enumerate(jobs):
            with st.container(border=True):
                st.subheader(job.get("title", "Untitled role"))
                st.write(f"**{job.get('company', 'Company not listed')}** · {job.get('location', 'Pakistan')}")
                st.write((job.get("description", "")[:400] + "…") if len(job.get("description", "")) > 400 else job.get("description", "No description provided."))
                if ai and st.button("Analyze match", key=f"match_{idx}"):
                    with st.spinner("Comparing resume with job description..."):
                        st.session_state[f"match_{idx}"] = match_job(profile, job, ai=ai)
                result = st.session_state.get(f"match_{idx}")
                if result:
                    st.metric("Estimated match", f"{result['match_score']} / 100")
                    st.write("**Matching skills:** " + ", ".join(result.get("matching_skills", [])))
                    st.write("**Skill gaps:** " + ", ".join(result.get("missing_skills", [])))
                c1, c2 = st.columns(2)
                with c1:
                    if st.button("Use for cover letter", key=f"cover_{idx}"):
                        st.session_state.selected_job = job
                        st.session_state.nav_page = "Cover Letter"
                        st.rerun()
                with c2:
                    if job.get("url"):
                        st.link_button("Open listing", job["url"])

    st.divider()
    st.subheader("Analyze a job you found elsewhere")
    manual_title = st.text_input("Job title", key="manual_job_title")
    manual_company = st.text_input("Company", key="manual_company")
    manual_url = st.text_input("Job URL (optional)", key="manual_job_url")
    manual_desc = st.text_area("Paste job description", height=180, key="manual_job_desc")
    if st.button("Analyze pasted job", key="analyze_manual"):
        if not st.session_state.resume_text:
            st.warning("Parse your resume first on the Resume Profile page.")
        elif len(manual_desc.strip()) < 30:
            st.warning("Paste a fuller job description for a useful comparison.")
        else:
            job = {"title": manual_title.strip() or "Target role", "company": manual_company.strip() or "Not specified", "location": location if 'location' in locals() else "Pakistan", "description": manual_desc.strip(), "url": manual_url.strip()}
            st.session_state.selected_job = job
            if ai:
                with st.spinner("Analyzing job match..."):
                    result = match_job(profile, job, ai=ai)
                st.session_state.manual_match = result
                st.metric("Estimated match", f"{result['match_score']} / 100")
                st.write("**Matching skills:** " + ", ".join(result.get("matching_skills", [])))
                st.write("**Missing skills:** " + ", ".join(result.get("missing_skills", [])))
                st.write("**Recommendations:**")
                for item in result.get("recommendations", []):
                    st.write(f"- {item}")
            else:
                st.warning("Add GEMINI_API_KEY to enable AI job matching.")


def render_cover_letter(ai: GeminiService | None) -> None:
    st.header("3. Cover letter generator")
    profile = st.session_state.profile or {}
    job = st.session_state.selected_job or {}
    if not st.session_state.resume_text:
        st.warning("Upload and parse your resume first.")
    with st.form("cover_letter_form"):
        title = st.text_input("Job title", value=job.get("title", ""))
        company = st.text_input("Company", value=job.get("company", ""))
        description = st.text_area("Job description", value=job.get("description", ""), height=180)
        tone = st.selectbox("Tone", ["Professional", "Warm and confident", "Concise"])
        submitted = st.form_submit_button("Generate cover letter", type="primary")
    if submitted:
        if not st.session_state.resume_text:
            st.error("Parse your resume before generating a cover letter.")
        elif not ai:
            st.error("Add GEMINI_API_KEY to enable cover-letter generation.")
        elif not description.strip():
            st.error("Add a job description for a tailored cover letter.")
        else:
            with st.spinner("Drafting your cover letter..."):
                try:
                    st.session_state.cover_letter = generate_cover_letter(
                        ai, st.session_state.resume_text, {"title": title, "company": company, "description": description}, tone
                    )
                    st.session_state.cover_letter_editor = st.session_state.cover_letter
                    st.session_state.selected_job = {"title": title, "company": company, "description": description, "url": job.get("url", "")}
                except Exception as exc:
                    st.error(f"Could not generate the letter: {exc}")
    if st.session_state.cover_letter:
        st.text_area("Edit your cover letter", key="cover_letter_editor", value=st.session_state.cover_letter, height=360)
        edited = st.session_state.get("cover_letter_editor", st.session_state.cover_letter)
        st.download_button("Download cover letter (.txt)", data=edited, file_name="cover_letter.txt", mime="text/plain")
        docx_buffer = BytesIO()
        from docx import Document
        document = Document()
        for paragraph in edited.split("\n"):
            document.add_paragraph(paragraph)
        document.save(docx_buffer)
        st.download_button("Download cover letter (.docx)", data=docx_buffer.getvalue(), file_name="cover_letter.docx", mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document")


def render_tracker(store: SupabaseStore | None, logged_in: bool) -> None:
    st.header("4. My applications")
    if not logged_in:
        st.info("Sign in using Supabase to save applications persistently. Until then, this tracker is limited to the current browser session.")
    with st.form("add_application_form"):
        c1, c2 = st.columns(2)
        with c1:
            title = st.text_input("Job title", value=(st.session_state.selected_job or {}).get("title", ""))
            company = st.text_input("Company", value=(st.session_state.selected_job or {}).get("company", ""))
            url = st.text_input("Application URL", value=(st.session_state.selected_job or {}).get("url", ""))
        with c2:
            status = st.selectbox("Status", ["Saved", "Planning to Apply", "Applied", "Interview", "Assessment", "Offer", "Rejected"])
            applied_on = st.date_input("Date", value=date.today())
        notes = st.text_area("Notes", placeholder="Recruiter contact, follow-up date, or interview notes")
        add = st.form_submit_button("Save application", type="primary")
    if add:
        record = {"title": title.strip(), "company": company.strip(), "url": url.strip(), "status": status, "applied_on": applied_on.isoformat(), "notes": notes.strip()}
        if not record["title"]:
            st.error("Job title is required.")
        elif logged_in and store:
            try:
                store.add_application(record)
                st.success("Application saved to Supabase.")
            except Exception as exc:
                st.error(f"Could not save to Supabase: {exc}")
        else:
            st.session_state.local_applications = st.session_state.get("local_applications", [])
            st.session_state.local_applications.append({**record, "id": f"local-{len(st.session_state.local_applications)+1}"})
            st.success("Application saved for this session only.")

    try:
        records = store.list_applications() if logged_in and store else st.session_state.get("local_applications", [])
    except Exception as exc:
        st.error(f"Could not load applications: {exc}")
        records = []
    if records:
        df = pd.DataFrame(records)
        if "status" in df.columns:
            counts = df["status"].value_counts()
            c1, c2, c3 = st.columns(3)
            c1.metric("Applications", len(df))
            c2.metric("Interviews", int(counts.get("Interview", 0)))
            c3.metric("Offers", int(counts.get("Offer", 0)))
        display_cols = [c for c in ["title", "company", "status", "applied_on", "url", "notes"] if c in df.columns]
        st.dataframe(df[display_cols], use_container_width=True, hide_index=True)
        if logged_in and store:
            ids = {str(r.get("id")): f"{r.get('title','Job')} — {r.get('company','Company')}" for r in records if r.get("id")}
            if ids:
                selected_id = st.selectbox("Select an application to update", options=list(ids), format_func=lambda x: ids[x])
                updated_status = st.selectbox("New status", ["Saved", "Planning to Apply", "Applied", "Interview", "Assessment", "Offer", "Rejected"], key="update_status")
                if st.button("Update status"):
                    try:
                        store.update_status(selected_id, updated_status)
                        st.success("Status updated.")
                        st.rerun()
                    except Exception as exc:
                        st.error(f"Could not update status: {exc}")


def main() -> None:
    init_state()
    st.title("🎯 AI Job Application Assistant")
    st.caption("Find relevant Pakistan jobs, understand your match, draft cover letters, and track applications.")
    store = get_store()
    logged_in = render_auth(store)
    ai = get_ai()
    if not ai:
        st.sidebar.warning("Gemini is not configured. Add GEMINI_API_KEY to enable AI extraction, matching, and cover letters. Basic resume parsing still works.")
    page = st.sidebar.radio("Navigation", ["Dashboard", "Resume Profile", "Find Jobs", "Cover Letter", "My Applications"], key="nav_page")
    if page == "Dashboard":
        st.subheader("Your job search workspace")
        c1, c2, c3 = st.columns(3)
        c1.metric("Resume loaded", "Yes" if st.session_state.resume_text else "No")
        c2.metric("Jobs found", len(st.session_state.get("job_results", [])))
        c3.metric("Applications tracked", len(st.session_state.get("local_applications", [])))
        st.markdown("#### Start here")
        st.markdown("1. **Resume Profile:** upload a PDF, DOCX, or TXT resume.\n2. **Find Jobs:** search Pakistan job links or analyze a pasted job description.\n3. **Cover Letter:** generate and download a tailored draft.\n4. **My Applications:** save and update application status.")
        st.info("Job listings are not guaranteed to be complete or current. Verify every vacancy and application deadline on the employer's official site.")
    elif page == "Resume Profile":
        render_resume_tab(ai)
    elif page == "Find Jobs":
        render_jobs_tab(ai)
    elif page == "Cover Letter":
        render_cover_letter(ai)
    elif page == "My Applications":
        render_tracker(get_current_store(store), logged_in)


if __name__ == "__main__":
    main()
