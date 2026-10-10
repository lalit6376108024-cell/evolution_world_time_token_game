# Evolution World — Real-Life Time Token Game

A responsive Flask website prototype where players log real-life activities, confirm their time, earn time tokens, spend tokens in an interactive game session, complete quests, and compare lifetime earned time on a leaderboard.

## Features in this first version

- Account registration and sign-in with Werkzeug password hashing.
- Activity timer with player confirmation.
- 1 token per complete minute of confirmed activity, capped at 240 minutes per session.
- One shared token wallet per player.
- Evolution levels based on lifetime tokens earned.
- Quest rewards, claimable once per account.
- Server-backed game sessions that spend one token per minute.
- Global leaderboard based on lifetime activity-earned tokens.
- Responsive desktop/mobile UI.
- SQLite database for local development and a `/health` endpoint for deployment checks.

## Important prototype limitations

- Activity duration is self-reported after using a timer; it is **not independently verified**. A determined user can leave the timer running. Do not treat this as proof of exercise, study, or other activity.
- The game is a lightweight interactive arena prototype, not a complete 3D RPG or real-time multiplayer world. Accounts and leaderboard are shared, but players do not yet see each other in a live shared world.
- SQLite is suitable for local testing. For a serious public deployment, use a managed PostgreSQL database and persistent storage. Render's local filesystem may be ephemeral; do not rely on a local SQLite file surviving redeploys or restarts.
- A client heartbeat is not a tamper-proof anti-cheat system. For a public launch, use PostgreSQL transactions, session leases, CSRF protection, rate limiting, email verification, password reset, abuse monitoring, and tests.
- This prototype does not accept payments and has no cash-out or transferable tokens.

## Run locally on Windows

1. Install Python 3.11 or 3.12 from https://www.python.org/downloads/.
2. Open PowerShell in the extracted project folder.
3. Create a virtual environment:

   ```powershell
   py -3.12 -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```

4. Install dependencies:

   ```powershell
   python -m pip install --upgrade pip
   python -m pip install -r requirements.txt
   ```

5. Set a secret for this PowerShell session:

   ```powershell
   $env:SECRET_KEY = "replace-this-with-a-long-random-secret"
   ```

6. Run the app:

   ```powershell
   python app.py
   ```

7. Visit http://127.0.0.1:5000.

If port 5000 is already occupied, use a different port:

```powershell
$env:PORT = "5050"
python app.py
```

Then visit http://127.0.0.1:5050.

## Publish to GitHub

1. Create a new empty repository on https://github.com (for example, `evolution-world`).
2. Extract this ZIP file.
3. In PowerShell, change directory into the extracted folder.
4. Run:

   ```powershell
   git init
   git add .
   git commit -m "Build Evolution World time-token game"
   git branch -M main
   git remote add origin https://github.com/YOUR-USERNAME/evolution-world.git
   git push -u origin main
   ```

Replace `YOUR-USERNAME` with your GitHub username. Install Git for Windows if `git` is not recognized.

## Deploy on Render

### Option A — Blueprint (recommended for this starter)

1. Push the project to GitHub.
2. Sign in to https://render.com.
3. Choose **New +** → **Blueprint**.
4. Connect GitHub and select this repository.
5. Render reads `render.yaml`; review and create the service.
6. Wait for deployment, then open the generated `onrender.com` URL.
7. Test `/health`, register two accounts, confirm activity sessions, and verify leaderboard entries.

`render.yaml` generates a `SECRET_KEY` for the service. The app uses SQLite in this prototype, so data may be lost on redeploy/restart or when the instance's filesystem is replaced. Use managed PostgreSQL before relying on persistent player accounts or wallet balances.

### Option B — Web Service

- **Build command:** `pip install -r requirements.txt`
- **Start command:** `gunicorn app:app --workers 2 --threads 4 --timeout 60`
- Add environment variable `SECRET_KEY` with a long random value.
- Health check path: `/health`.

## Suggested next production upgrades

1. Replace SQLite with Render PostgreSQL and migrations.
2. Add CSRF protection, rate limits, account recovery, and stronger session handling.
3. Implement a fair activity verification approach (manual review or opt-in device integrations).
4. Add real multiplayer gameplay (WebSockets and authoritative game server).
5. Add persistent character inventory, save slots, richer quests, and game-specific progression.
6. Add automated tests for wallet accounting and session concurrency.
