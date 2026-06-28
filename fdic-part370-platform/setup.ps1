# =============================================================================
# FDIC Part 370 Platform — one-shot local setup (Windows / PowerShell)
#
#   ./setup.ps1            full setup (deps, env, tests, evals, optional seeds)
#   ./setup.ps1 -SkipDeps  skip pip/npm install (faster re-run)
#
# External seeds (Snowflake, Pinecone, LangSmith) self-guard: they run only if
# the matching keys are present in backend/.env, otherwise they print a note.
# =============================================================================
param([switch]$SkipDeps)

$ErrorActionPreference = "Continue"
$root = $PSScriptRoot
function Step($msg) { Write-Host "`n=== $msg ===" -ForegroundColor Cyan }

# 1. backend/.env --------------------------------------------------------------
Step "Environment file"
if (-not (Test-Path "$root\backend\.env")) {
    Copy-Item "$root\.env.example" "$root\backend\.env"
    Write-Host "Created backend/.env from .env.example"
} else {
    Write-Host "backend/.env already exists — leaving it as-is"
}

# 2. Backend dependencies ------------------------------------------------------
if (-not $SkipDeps) {
    Step "Backend dependencies (pip)"
    python -m pip install -r "$root\backend\requirements.txt"
}

# 3. Backend tests -------------------------------------------------------------
Step "Backend tests (pytest)"
Push-Location "$root\backend"
python -m pytest -q

# 4. Eval suite (always works, no key needed) ----------------------------------
Step "Eval suite — one labeled example per ORC"
python scripts\seed_langsmith_dataset.py --local

# 5. Optional external setups (self-guard on missing keys) ---------------------
Step "Snowflake schema (runs only if SNOWFLAKE_ACCOUNT is set)"
python scripts\init_snowflake.py
Step "Pinecone RAG index (runs only if PINECONE_API_KEY + OPENAI_API_KEY set)"
python scripts\seed_pinecone.py
Pop-Location

# 6. Frontend dependencies -----------------------------------------------------
if (-not $SkipDeps) {
    Step "Frontend dependencies (npm)"
    Push-Location "$root\frontend"
    npm install
    Pop-Location
}

# 7. Done ----------------------------------------------------------------------
Step "Setup complete"
Write-Host @"
Start the platform:
  Backend :  cd backend ;  python -m uvicorn app.main:app --port 8000     -> http://127.0.0.1:8000/docs
  Frontend:  cd frontend ; npm run dev                                    -> http://localhost:5173

Enable integrations by filling keys in backend/.env, then re-run ./setup.ps1:
  - LANGSMITH_API_KEY + LANGSMITH_TRACING=true   then: python backend/scripts/seed_langsmith_dataset.py --run
  - SNOWFLAKE_* credentials                       (Snowflake schema auto-created above)
  - PINECONE_API_KEY + OPENAI_API_KEY             (Pinecone index auto-seeded above)
"@ -ForegroundColor Green
