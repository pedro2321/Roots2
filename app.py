from flask import Flask, render_template, request, redirect, url_for, abort
import os
import hashlib

# try to import postgres driver only if DATABASE_URL present
DATABASE_URL = os.getenv("DATABASE_URL")

USE_POSTGRES = False
if DATABASE_URL:
    import psycopg2
    import psycopg2.extras
    USE_POSTGRES = True
else:
    import sqlite3

app = Flask(__name__)


# -----------------------
# Database helpers
# -----------------------
def get_conn():
    """Return a new DB connection (postgres or sqlite)."""
    if USE_POSTGRES:
        conn = psycopg2.connect(DATABASE_URL)
        return conn
    else:
        conn = sqlite3.connect("database.db", check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn


def init_tables():
    """Create tables if missing. Safe to call multiple times."""
    conn = get_conn()
    try:
        cur = conn.cursor()
        if USE_POSTGRES:
            # use TEXT and SERIAL for Postgres
            cur.execute("""
                CREATE TABLE IF NOT EXISTS houses (
                    id SERIAL PRIMARY KEY,
                    name TEXT UNIQUE NOT NULL
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS threads (
                    id SERIAL PRIMARY KEY,
                    house_id INTEGER NOT NULL REFERENCES houses(id),
                    title TEXT NOT NULL
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS posts (
                    id SERIAL PRIMARY KEY,
                    thread_id INTEGER NOT NULL REFERENCES threads(id),
                    nickname TEXT NOT NULL,
                    tripcode_hash TEXT NOT NULL,
                    content TEXT NOT NULL
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS replies (
                    id SERIAL PRIMARY KEY,
                    post_id INTEGER NOT NULL REFERENCES posts(id),
                    nickname TEXT NOT NULL,
                    tripcode_hash TEXT NOT NULL,
                    content TEXT NOT NULL
                )
            """)
            conn.commit()
        else:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS houses (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE NOT NULL
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS threads (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    house_id INTEGER NOT NULL,
                    title TEXT NOT NULL
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS posts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    thread_id INTEGER NOT NULL,
                    nickname TEXT NOT NULL,
                    tripcode_hash TEXT NOT NULL,
                    content TEXT NOT NULL
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS replies (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    post_id INTEGER NOT NULL,
                    nickname TEXT NOT NULL,
                    tripcode_hash TEXT NOT NULL,
                    content TEXT NOT NULL
                )
            """)
            conn.commit()
    finally:
        cur.close()
        conn.close()


# run once at import (safe)
init_tables()


def gen_trip(trip):
    if trip is None:
        trip = ""
    return hashlib.sha256(trip.encode()).hexdigest()


# -----------------------
# Utility small wrappers
# -----------------------
def fetchall(query, params=()):
    conn = get_conn()
    try:
        if USE_POSTGRES:
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute(query, params)
            rows = cur.fetchall()
            return rows
        else:
            cur = conn.cursor()
            cur.execute(query, params)
            rows = cur.fetchall()
            # sqlite3.Row supports both index and name access in templates
            return rows
    finally:
        cur.close()
        conn.close()


def fetchone(query, params=()):
    conn = get_conn()
    try:
        if USE_POSTGRES:
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute(query, params)
            row = cur.fetchone()
            return row
        else:
            cur = conn.cursor()
            cur.execute(query, params)
            row = cur.fetchone()
            return row
    finally:
        cur.close()
        conn.close()


def execute(query, params=()):
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(query, params)
        if USE_POSTGRES:
            # for inserts returning id, caller should SELECT RETURNING themselves
            conn.commit()
            try:
                return cur.fetchone()  # might be None
            except Exception:
                return None
        else:
            conn.commit()
            # sqlite cursor has lastrowid
            return cur.lastrowid
    finally:
        cur.close()
        conn.close()


# -----------------------
# Routes
# -----------------------
@app.route("/")
def index():
    # homepage: list houses (most recent first)
    houses = fetchall("SELECT * FROM houses ORDER BY id DESC")
    return render_template("index.html", houses=houses)


@app.route("/house/new", methods=["GET", "POST"])
def new_house():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        if not name:
            return "Empty name", 400
        try:
            if USE_POSTGRES:
                # RETURNING id ensures consistent behavior
                conn = get_conn()
                cur = conn.cursor()
                try:
                    cur.execute("INSERT INTO houses (name) VALUES (%s) RETURNING id", (name,))
                    conn.commit()
                    cur.close()
                    conn.close()
                    return redirect(url_for("index"))
                except Exception as e:
                    conn.rollback()
                    cur.close()
                    conn.close()
                    # unique violation or other error
                    return "House name already taken or DB error", 400
            else:
                execute("INSERT INTO houses (name) VALUES (?)", (name,))
                return redirect(url_for("index"))
        except Exception:
            return "Database error", 500
    return render_template("new_house.html")


@app.route("/house/<int:house_id>")
def house_view(house_id):
    house = fetchone("SELECT * FROM houses WHERE id=%s" % ("%s" if USE_POSTGRES else "?"), (house_id,))
    if not house:
        abort(404)
    threads = fetchall("SELECT * FROM threads WHERE house_id=%s ORDER BY id DESC" % ("%s" if USE_POSTGRES else "?"), (house_id,))
    return render_template("house.html", house=house, threads=threads)


@app.route("/house/<int:house_id>/thread/new", methods=["GET", "POST"])
def new_thread(house_id):
    # check house exists
    h = fetchone("SELECT * FROM houses WHERE id=%s" % ("%s" if USE_POSTGRES else "?"), (house_id,))
    if not h:
        abort(404)
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        nickname = request.form.get("nickname", "").strip()
        tripcode = request.form.get("tripcode", "")
        content = request.form.get("content", "").strip()
        if not title or not nickname or not content:
            return "Missing fields", 400

        trip_hash = gen_trip(tripcode)

        if USE_POSTGRES:
            conn = get_conn()
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            try:
                cur.execute("INSERT INTO threads (house_id, title) VALUES (%s, %s) RETURNING id", (house_id, title))
                thread_row = cur.fetchone()
                thread_id = thread_row["id"]
                cur.execute("INSERT INTO posts (thread_id, nickname, tripcode_hash, content) VALUES (%s, %s, %s, %s)",
                            (thread_id, nickname, trip_hash, content))
                conn.commit()
                cur.close()
                conn.close()
                return redirect(url_for("thread_view", thread_id=thread_id))
            except Exception:
                conn.rollback()
                cur.close()
                conn.close()
                return "DB error", 500
        else:
            conn = get_conn()
            cur = conn.cursor()
            try:
                cur.execute("INSERT INTO threads (house_id, title) VALUES (?, ?)", (house_id, title))
                thread_id = cur.lastrowid
                cur.execute("INSERT INTO posts (thread_id, nickname, tripcode_hash, content) VALUES (?, ?, ?, ?)",
                            (thread_id, nickname, trip_hash, content))
                conn.commit()
                cur.close()
                conn.close()
                return redirect(url_for("thread_view", thread_id=thread_id))
            except Exception:
                conn.rollback()
                cur.close()
                conn.close()
                return "DB error", 500

    # GET
    return render_template("new_thread.html", house_id=house_id, house=h)


@app.route("/thread/<int:thread_id>")
def thread_view(thread_id):
    # fetch thread including house_id
    if USE_POSTGRES:
        thread = fetchone("SELECT * FROM threads WHERE id=%s", (thread_id,))
    else:
        thread = fetchone("SELECT * FROM threads WHERE id=?", (thread_id,))
    if not thread:
        abort(404)

    # fetch posts and replies
    if USE_POSTGRES:
        conn = get_conn()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("SELECT * FROM posts WHERE thread_id=%s ORDER BY id ASC", (thread_id,))
        posts = cur.fetchall()
        # attach replies to each post
        for p in posts:
            cur.execute("SELECT * FROM replies WHERE post_id=%s ORDER BY id ASC", (p["id"],))
            p["replies"] = cur.fetchall()
        cur.close()
        conn.close()
    else:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("SELECT * FROM posts WHERE thread_id=? ORDER BY id ASC", (thread_id,))
        rows = cur.fetchall()
        posts = []
        for r in rows:
            # convert sqlite3.Row to dict for easier template handling
            post = dict(r)
            cur2 = conn.cursor()
            cur2.execute("SELECT * FROM replies WHERE post_id=? ORDER BY id ASC", (post["id"],))
            post["replies"] = [dict(rr) for rr in cur2.fetchall()]
            cur2.close()
            posts.append(post)
        cur.close()
        conn.close()

    return render_template("thread.html", thread=thread, posts=posts)


@app.route("/post/<int:post_id>/reply", methods=["POST"])
def reply(post_id):
    nickname = request.form.get("nickname", "").strip()
    tripcode = request.form.get("tripcode", "")
    content = request.form.get("content", "").strip()
    if not nickname or not content:
        return "Missing fields", 400
    trip_hash = gen_trip(tripcode)

    # need to find thread_id for redirect later
    if USE_POSTGRES:
        conn = get_conn()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        try:
            cur.execute("INSERT INTO replies (post_id, nickname, tripcode_hash, content) VALUES (%s, %s, %s, %s)",
                        (post_id, nickname, trip_hash, content))
            cur.execute("SELECT thread_id FROM posts WHERE id=%s", (post_id,))
            thread_id = cur.fetchone()["thread_id"]
            conn.commit()
            cur.close()
            conn.close()
            return redirect(url_for("thread_view", thread_id=thread_id))
        except Exception:
            conn.rollback()
            cur.close()
            conn.close()
            return "DB error", 500
    else:
        conn = get_conn()
        cur = conn.cursor()
        try:
            cur.execute("INSERT INTO replies (post_id, nickname, tripcode_hash, content) VALUES (?, ?, ?, ?)",
                        (post_id, nickname, trip_hash, content))
            cur.execute("SELECT thread_id FROM posts WHERE id=?", (post_id,))
            thread_id = cur.fetchone()["thread_id"]
            conn.commit()
            cur.close()
            conn.close()
            return redirect(url_for("thread_view", thread_id=thread_id))
        except Exception:
            conn.rollback()
            cur.close()
            conn.close()
            return "DB error", 500


# -----------------------
# Run
# -----------------------
if __name__ == "__main__":
    # local dev: sqlite fallback will run here
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)), debug=True)
