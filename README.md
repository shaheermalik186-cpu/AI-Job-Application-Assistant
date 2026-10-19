# AI-Job-Application-Assistant
AI Job Application Assistant
A Streamlit portfolio project for Pakistan job seekers. It supports resume parsing, AI profile extraction, job-search links and optional Adzuna API lookup, resume-to-job matching, cover-letter drafting, and a Supabase-backed application tracker.
Important limitations: job-provider coverage for Pakistan depends on the provider and account. The app does not scrape LinkedIn, Rozee.pk, Indeed, or other job boards. If the optional Adzuna endpoint does not support Pakistan for your account, use the provided search links or paste a job description manually. Verify every vacancy on the employer's official website. Match scores are estimates, not an employer's ATS score.

Features
1. Resume profile: PDF, DOCX, and TXT parsing; Gemini extraction when configured; local heuristic fallback.
2. Job discovery: Pakistan-focused web search links, optional Adzuna API lookup, and manual job-description input.
3. Job matching: Gemini-based comparison or a clearly labeled keyword heuristic fallback.
4. Cover letters: tailored draft generation and TXT/DOCX downloads. Review the letter before sending.
5. Application tracking: Supabase Auth + PostgreSQL, status changes, notes, and per-user row-level security.
Requirements
- Python 3.11 recommended
- Google Gemini API key from Google AI Studio
- Supabase project for persistent account-based tracking
- Optional Adzuna API credentials; confirm Pakistan country coverage with the provider
Run locally
1. Create and activate a virtual environment
Windows PowerShell:
py -3.11 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
macOS/Linux:
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
2. Configure secrets
Copy .streamlit/secrets.toml.example to .streamlit/secrets.toml and fill in your real values:
GEMINI_API_KEY = "your_gemini_api_key"
GEMINI_MODEL = "gemini-flash-latest"
SUPABASE_URL = "https://your-project.supabase.co"
SUPABASE_ANON_KEY = "your_supabase_anon_key"
ADZUNA_APP_ID = ""
ADZUNA_APP_KEY = ""
Do not commit secrets.toml, API keys, or real resumes. The .gitignore excludes local secrets.
3. Set up Supabase
1. Create a project at Supabase.
2. In the dashboard, open SQL Editor.
3. Run the contents of supabase_schema.sql to create the applications table and per-user Row Level Security policies.
4. In Authentication > Providers, ensure Email authentication is enabled.
5. Copy the project URL and anon/publishable key into local secrets. Never put a service-role key in this Streamlit app.
6. For quick local testing, you can disable email confirmation in Supabase Auth settings; for a real public app, configure email confirmation properly.
4. Run the app
streamlit run app.py
Open the local URL printed in the terminal (normally http://localhost:8501). Create an account in the sidebar, then sign in. Resume parsing works without Gemini, but AI profile extraction, semantic matching, and cover-letter generation need a valid Gemini key.
Job search notes for Pakistan
The app generates search links for Google Jobs/web search, Rozee.pk-indexed pages, and LinkedIn job search. These are links, not scraped or guaranteed-live listings. If you configure Adzuna credentials, the app tries the pk country endpoint; Adzuna's available countries and account access can vary, so the UI handles provider errors and falls back to search links. Do not assume a provider supports Pakistan until you verify it with your API account.

For reliable matching, paste the full job description and the official application URL. Always check the original employer listing for closing dates and requirements.
Test
pytest -q
Tests cover TXT parsing, empty/unsupported file handling, heuristic profile extraction, keyword match bounds, and search-link generation. These tests do not call Gemini or Supabase. Live API testing requires your credentials and network access.
Deploy to Streamlit Community Cloud
1. Push the project to a GitHub repository.
2. Open Streamlit Community Cloud and connect GitHub.
3. Choose the repository, main branch, and app.py as the main file.
4. In the app's Settings > Secrets, add the same TOML keys as above (with real values). Do not upload .streamlit/secrets.toml to GitHub.
5. Deploy and check logs. If a dependency build fails, review the error and use the package version ranges in requirements.txt.
GitHub UI upload
1. Create a repository on GitHub.
2. Use Add file > Upload files to upload the project files/folders, including modules/, tests/, supabase_schema.sql, and requirements.txt.
3. Commit changes. Verify .streamlit/secrets.toml is not in the repository.
Privacy and security
- Resume text is held in Streamlit session state for the current session and is not automatically stored in Supabase.
- Do not upload sensitive resumes to public repositories or paste secrets into chat.
- Supabase policies in supabase_schema.sql restrict application records to the signed-in user. Never replace the anon key with a service-role key in a public client app.
- Add a privacy notice and deletion/export controls before inviting public users. For production, review retention, rate limits, abuse prevention, and provider terms.
Project structure
ai_job_application_assistant/
├── app.py
├── requirements.txt
├── README.md
├── supabase_schema.sql
├── .gitignore
├── .streamlit/
│   └── secrets.toml.example
├── modules/
│   ├── __init__.py
│   ├── resume_parser.py
│   ├── gemini_service.py
│   ├── job_search.py
│   ├── job_matcher.py
│   ├── cover_letter.py
│   └── database.py
└── tests/
    ├── test_resume_parser.py
    └── test_job_matcher.py
