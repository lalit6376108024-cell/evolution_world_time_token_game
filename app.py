import os, sqlite3, secrets, hashlib, hmac, time
from datetime import datetime, timezone, date
from functools import wraps
from flask import Flask, g, request, session, redirect, url_for, render_template, flash, jsonify
from werkzeug.security import generate_password_hash, check_password_hash

APP_SECRET = os.environ.get("SECRET_KEY")
if not APP_SECRET:
    # Development fallback only. Set SECRET_KEY in Render for persistent secure sessions.
    APP_SECRET = "dev-only-change-this-secret-" + secrets.token_hex(16)

app = Flask(__name__)
app.secret_key = APP_SECRET
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.environ.get("COOKIE_SECURE", "0") == "1",
    PERMANENT_SESSION_LIFETIME=60 * 60 * 24 * 14,
    MAX_CONTENT_LENGTH=1_000_000,
)
DB_PATH = os.environ.get("DATABASE_PATH", os.path.join(os.path.dirname(__file__), "game.db"))
ACTIVITY_TYPES = ["Exercise", "Study", "Reading", "Skill practice", "Creative work", "Mindfulness", "Other"]

def connect_db():
    conn = sqlite3.connect(DB_PATH, timeout=20)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def init_db():
    conn = connect_db()
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS users (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      username TEXT NOT NULL COLLATE NOCASE UNIQUE,
      password_hash TEXT NOT NULL,
      created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS activity_sessions (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      activity TEXT NOT NULL,
      started_at INTEGER NOT NULL,
      ended_at INTEGER,
      seconds INTEGER,
      confirmed INTEGER NOT NULL DEFAULT 0,
      awarded INTEGER NOT NULL DEFAULT 0
    );
    CREATE TABLE IF NOT EXISTS wallet (
      user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
      balance INTEGER NOT NULL DEFAULT 0,
      lifetime_earned INTEGER NOT NULL DEFAULT 0
    );
    CREATE TABLE IF NOT EXISTS game_sessions (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      started_at INTEGER NOT NULL,
      last_seen INTEGER NOT NULL,
      ended_at INTEGER,
      spent INTEGER NOT NULL DEFAULT 0
    );
    CREATE TABLE IF NOT EXISTS quest_completions (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      quest_key TEXT NOT NULL,
      completed_at TEXT NOT NULL,
      UNIQUE(user_id, quest_key)
    );
    """)
    conn.commit()
    conn.close()

init_db()

def now_ts():
    return int(time.time())

def current_user():
    uid = session.get("user_id")
    if not uid:
        return None
    conn = connect_db()
    user = conn.execute("SELECT id, username, created_at FROM users WHERE id=?", (uid,)).fetchone()
    conn.close()
    return user

@app.before_request
def load_user():
    g.user = current_user()

def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not g.user:
            flash("Please sign in to continue.", "info")
            return redirect(url_for("login"))
        return fn(*args, **kwargs)
    return wrapper

def active_game(conn, uid):
    return conn.execute(
        "SELECT * FROM game_sessions WHERE user_id=? AND ended_at IS NULL ORDER BY id DESC LIMIT 1",
        (uid,)
    ).fetchone()

@app.route("/")
def index():
    if g.user:
        return redirect(url_for("dashboard"))
    return render_template("landing.html")

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        if not (3 <= len(username) <= 20) or not all(c.isalnum() or c in "_-" for c in username):
            flash("Username must be 3–20 characters using letters, numbers, _ or -.", "error")
            return render_template("auth.html", mode="register")
        if len(password) < 10:
            flash("Use a password with at least 10 characters.", "error")
            return render_template("auth.html", mode="register")
        conn = connect_db()
        try:
            cur = conn.execute("INSERT INTO users(username,password_hash,created_at) VALUES(?,?,?)",
                               (username, generate_password_hash(password), datetime.now(timezone.utc).isoformat()))
            conn.execute("INSERT INTO wallet(user_id,balance,lifetime_earned) VALUES(?,0,0)", (cur.lastrowid,))
            conn.commit()
            session.clear()
            session["user_id"] = cur.lastrowid
            session.permanent = True
            flash("Welcome to Evolution World. Your journey begins now!", "success")
            return redirect(url_for("dashboard"))
        except sqlite3.IntegrityError:
            flash("That username is already taken.", "error")
        finally:
            conn.close()
    return render_template("auth.html", mode="register")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        conn = connect_db()
        user = conn.execute("SELECT * FROM users WHERE username=? COLLATE NOCASE", (username,)).fetchone()
        conn.close()
        if user and check_password_hash(user["password_hash"], password):
            session.clear()
            session["user_id"] = user["id"]
            session.permanent = True
            return redirect(url_for("dashboard"))
        flash("Username or password was incorrect.", "error")
    return render_template("auth.html", mode="login")

@app.route("/logout", methods=["POST"])
@login_required
def logout():
    session.clear()
    return redirect(url_for("index"))

@app.route("/dashboard")
@login_required
def dashboard():
    conn = connect_db()
    wallet = conn.execute("SELECT * FROM wallet WHERE user_id=?", (g.user["id"],)).fetchone()
    recent = conn.execute("SELECT * FROM activity_sessions WHERE user_id=? ORDER BY id DESC LIMIT 6", (g.user["id"],)).fetchall()
    stats = conn.execute("""
      SELECT COALESCE(SUM(CASE WHEN confirmed=1 THEN seconds ELSE 0 END),0) AS seconds,
             COUNT(CASE WHEN confirmed=1 THEN 1 END) AS sessions
      FROM activity_sessions WHERE user_id=?
    """, (g.user["id"],)).fetchone()
    quests = conn.execute("SELECT quest_key FROM quest_completions WHERE user_id=?", (g.user["id"],)).fetchall()
    done = {q["quest_key"] for q in quests}
    game = active_game(conn, g.user["id"])
    conn.close()
    level = 1 + wallet["lifetime_earned"] // 120
    return render_template("dashboard.html", wallet=wallet, recent=recent, stats=stats,
                           level=level, quests_done=done, game=game, activity_types=ACTIVITY_TYPES)

@app.route("/activity/start", methods=["POST"])
@login_required
def activity_start():
    activity = request.form.get("activity", "Other").strip()[:40]
    if not activity:
        activity = "Other"
    conn = connect_db()
    existing = conn.execute("SELECT id FROM activity_sessions WHERE user_id=? AND ended_at IS NULL",
                            (g.user["id"],)).fetchone()
    if existing:
        conn.close()
        flash("Finish your current activity timer first.", "error")
        return redirect(url_for("dashboard"))
    conn.execute("INSERT INTO activity_sessions(user_id,activity,started_at) VALUES(?,?,?)",
                 (g.user["id"], activity, now_ts()))
    conn.commit()
    conn.close()
    flash(f"Timer started: {activity}. Keep this tab open or return when finished.", "success")
    return redirect(url_for("dashboard"))

@app.route("/activity/stop", methods=["POST"])
@login_required
def activity_stop():
    conn = connect_db()
    row = conn.execute("SELECT * FROM activity_sessions WHERE user_id=? AND ended_at IS NULL ORDER BY id DESC LIMIT 1",
                       (g.user["id"],)).fetchone()
    if not row:
        conn.close()
        flash("There is no active activity timer.", "error")
        return redirect(url_for("dashboard"))
    ended = now_ts()
    # Limit one claim to 4 hours; longer sessions require restarting the timer.
    seconds = max(0, min(ended - row["started_at"], 4 * 60 * 60))
    conn.execute("UPDATE activity_sessions SET ended_at=?, seconds=? WHERE id=?", (ended, seconds, row["id"]))
    conn.commit()
    conn.close()
    flash(f"Timer stopped at {seconds // 60} minutes. Confirm the activity to claim tokens.", "info")
    return redirect(url_for("confirm_activity", session_id=row["id"]))

@app.route("/activity/confirm/<int:session_id>", methods=["GET", "POST"])
@login_required
def confirm_activity(session_id):
    conn = connect_db()
    row = conn.execute("SELECT * FROM activity_sessions WHERE id=? AND user_id=?",
                       (session_id, g.user["id"])).fetchone()
    if not row:
        conn.close()
        flash("Activity session not found.", "error")
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        if row["ended_at"] is None:
            conn.close()
            flash("Stop the timer before confirming.", "error")
            return redirect(url_for("dashboard"))
        if not row["confirmed"]:
            # 1 token per complete minute, with a conservative 240-minute cap per session.
            tokens = min(240, max(0, row["seconds"] // 60))
            conn.execute("UPDATE activity_sessions SET confirmed=1, awarded=? WHERE id=? AND confirmed=0",
                         (tokens, row["id"]))
            conn.execute("UPDATE wallet SET balance=balance+?, lifetime_earned=lifetime_earned+? WHERE user_id=?",
                         (tokens, tokens, g.user["id"]))
            conn.commit()
        conn.close()
        flash("Activity confirmed. Your tokens are ready to spend!", "success")
        return redirect(url_for("dashboard"))
    conn.close()
    return render_template("confirm.html", activity=row)

@app.route("/game/start", methods=["POST"])
@login_required
def game_start():
    conn = connect_db()
    existing = active_game(conn, g.user["id"])
    if existing:
        conn.close()
        flash("You already have an active game session.", "error")
        return redirect(url_for("play"))
    wallet = conn.execute("SELECT balance FROM wallet WHERE user_id=?", (g.user["id"],)).fetchone()
    if wallet["balance"] < 1:
        conn.close()
        flash("Earn tokens with a real-life activity before playing.", "error")
        return redirect(url_for("dashboard"))
    ts = now_ts()
    cur = conn.execute("INSERT INTO game_sessions(user_id,started_at,last_seen) VALUES(?,?,?)",
                       (g.user["id"], ts, ts))
    conn.commit()
    conn.close()
    session["game_id"] = cur.lastrowid
    return redirect(url_for("play"))

@app.route("/play")
@login_required
def play():
    conn = connect_db()
    game = active_game(conn, g.user["id"])
    wallet = conn.execute("SELECT * FROM wallet WHERE user_id=?", (g.user["id"],)).fetchone()
    conn.close()
    if not game:
        return render_template("play.html", game=None, wallet=wallet)
    return render_template("play.html", game=game, wallet=wallet)

@app.route("/game/pulse", methods=["POST"])
@login_required
def game_pulse():
    data = request.get_json(silent=True) or {}
    conn = connect_db()
    game = active_game(conn, g.user["id"])
    wallet = conn.execute("SELECT balance FROM wallet WHERE user_id=?", (g.user["id"],)).fetchone()
    if not game:
        conn.close()
        return jsonify(ok=False, error="No active game session."), 400
    ts = now_ts()
    elapsed = max(0, min(ts - game["last_seen"], 30))
    # Bill elapsed time in whole-minute units, carrying partial minutes in last_seen only
    # by charging one token per minute once 60 seconds have accumulated since session start.
    total_elapsed = max(0, ts - game["started_at"])
    should_spend = total_elapsed // 60
    due = max(0, should_spend - game["spent"])
    due = min(due, wallet["balance"])
    if due:
        conn.execute("UPDATE wallet SET balance=balance-? WHERE user_id=? AND balance>=?", (due, g.user["id"], due))
        conn.execute("UPDATE game_sessions SET spent=spent+? WHERE id=?", (due, game["id"]))
    conn.execute("UPDATE game_sessions SET last_seen=? WHERE id=?", (ts, game["id"]))
    # Stop session when there are no tokens left and a full minute is due.
    new_spent = game["spent"] + due
    new_balance = wallet["balance"] - due
    out_of_tokens = new_balance <= 0 and new_spent > 0 and total_elapsed >= new_spent * 60
    if out_of_tokens:
        conn.execute("UPDATE game_sessions SET ended_at=? WHERE id=?", (ts, game["id"]))
    conn.commit()
    conn.close()
    return jsonify(ok=True, balance=new_balance, spent=new_spent, elapsed=total_elapsed,
                   ended=out_of_tokens, seconds_until_next=max(0, 60 - (total_elapsed % 60)))

@app.route("/game/stop", methods=["POST"])
@login_required
def game_stop():
    conn = connect_db()
    game = active_game(conn, g.user["id"])
    if game:
        conn.execute("UPDATE game_sessions SET ended_at=? WHERE id=?", (now_ts(), game["id"]))
        conn.commit()
    conn.close()
    flash("Game session ended. Your remaining tokens are safe.", "info")
    return redirect(url_for("dashboard"))

QUESTS = [
    {"key":"first_steps","title":"First Steps","description":"Confirm your first real-life activity session.","reward":10,"kind":"activity"},
    {"key":"time_keeper","title":"Time Keeper","description":"Earn at least 60 lifetime tokens.","reward":15,"kind":"tokens"},
    {"key":"world_builder","title":"World Builder","description":"Reach level 2 by earning 120 tokens.","reward":25,"kind":"level"},
]
@app.route("/quests")
@login_required
def quests():
    conn = connect_db()
    wallet = conn.execute("SELECT * FROM wallet WHERE user_id=?", (g.user["id"],)).fetchone()
    activity_count = conn.execute("SELECT COUNT(*) AS n FROM activity_sessions WHERE user_id=? AND confirmed=1", (g.user["id"],)).fetchone()["n"]
    completed = {r["quest_key"] for r in conn.execute("SELECT quest_key FROM quest_completions WHERE user_id=?", (g.user["id"],)).fetchall()}
    level = 1 + wallet["lifetime_earned"] // 120
    eligible = {"first_steps": activity_count >= 1, "time_keeper": wallet["lifetime_earned"] >= 60, "world_builder": level >= 2}
    conn.close()
    return render_template("quests.html", quests=QUESTS, completed=completed, eligible=eligible)

@app.route("/quests/claim/<quest_key>", methods=["POST"])
@login_required
def claim_quest(quest_key):
    quest = next((q for q in QUESTS if q["key"] == quest_key), None)
    if not quest:
        flash("Quest not found.", "error")
        return redirect(url_for("quests"))
    conn = connect_db()
    wallet = conn.execute("SELECT * FROM wallet WHERE user_id=?", (g.user["id"],)).fetchone()
    count = conn.execute("SELECT COUNT(*) AS n FROM activity_sessions WHERE user_id=? AND confirmed=1", (g.user["id"],)).fetchone()["n"]
    level = 1 + wallet["lifetime_earned"] // 120
    eligible = {"first_steps": count >= 1, "time_keeper": wallet["lifetime_earned"] >= 60, "world_builder": level >= 2}[quest_key]
    already = conn.execute("SELECT id FROM quest_completions WHERE user_id=? AND quest_key=?", (g.user["id"], quest_key)).fetchone()
    if eligible and not already:
        conn.execute("INSERT INTO quest_completions(user_id,quest_key,completed_at) VALUES(?,?,?)",
                     (g.user["id"], quest_key, datetime.now(timezone.utc).isoformat()))
        conn.execute("UPDATE wallet SET balance=balance+? WHERE user_id=?", (quest["reward"], g.user["id"]))
        conn.commit()
        flash(f"Quest claimed: +{quest['reward']} bonus tokens!", "success")
    else:
        flash("Quest is not yet eligible or has already been claimed.", "error")
    conn.close()
    return redirect(url_for("quests"))

@app.route("/leaderboard")
@login_required
def leaderboard():
    conn = connect_db()
    rows = conn.execute("""
      SELECT u.username, w.lifetime_earned,
             (SELECT COUNT(*) FROM activity_sessions a WHERE a.user_id=u.id AND a.confirmed=1) AS activities
      FROM users u JOIN wallet w ON u.id=w.user_id
      ORDER BY w.lifetime_earned DESC, activities DESC, u.username ASC LIMIT 50
    """).fetchall()
    own = next((i for i, r in enumerate(rows, 1) if r["username"].lower() == g.user["username"].lower()), None)
    conn.close()
    return render_template("leaderboard.html", rows=rows, own=own)

@app.route("/health")
def health():
    return jsonify(status="ok", service="evolution-world")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=False)
