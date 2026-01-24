from flask import Flask, render_template, request, redirect
import hashlib
import os

# DB imports (both)
import sqlite3
import psycopg2
import psycopg2.extras

app = Flask(__name__)

# -----------------------------
# Database setup (AUTO SWITCH)
# -----------------------------
USE_POSTGRES = "DATABASE_URL" in os.environ

def get_db():
    if USE_POSTGRES:
        conn = psycopg2.connect(os.environ["DATABASE_URL"])
        return conn
    else:
        conn = sqlite3.connect("database.db")
        conn.row_factory = sqlite3.Row
        return conn

def init_db():
    db = get_db()
    cur = db.cursor()

    if USE_POSTGRES:
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

    db.commit()
    cur.close()
    db.close()

init_db()

# -----------------------------
# Helpers
# -----------------------------
def hash_tripcode(trip):
    return hashlib.sha256(trip.encode()).hexdigest()

def cursor(db):
    if USE_POSTGRES:
        return db.cursor(cursor_factory=psycopg2.extras.DictCursor)
    return db.cursor()

# -----------------------------
# Routes
# -----------------------------
@app.route("/")
def index():
    db = get_db()
    cur = cursor(db)
    cur.execute("SELECT * FROM houses ORDER BY id DESC")
    houses = cur.fetchall()
    cur.close()
    db.close()
    return render_template("index.html", houses=houses)

@app.route("/house/new", methods=["GET", "POST"])
def new_house():
    if request.method == "POST":
        name = request.form["name"]
        db = get_db()
        cur = db.cursor()
        try:
            if USE_POSTGRES:
                cur.execute("INSERT INTO houses (name) VALUES (%s)", (name,))
            else:
                cur.execute("INSERT INTO houses (name) VALUES (?)", (name,))
            db.commit()
            return redirect("/")
        except Exception:
            db.rollback()
            return "House name already taken!"
        finally:
            cur.close()
            db.close()
    return render_template("new_house.html")

@app.route("/house/<int:house_id>")
def house(house_id):
    db = get_db()
    cur = cursor(db)
    q = "%s" if USE_POSTGRES else "?"
    cur.execute(f"SELECT * FROM houses WHERE id={q}", (house_id,))
    house = cur.fetchone()
    cur.execute(f"SELECT * FROM threads WHERE house_id={q} ORDER BY id DESC", (house_id,))
    threads = cur.fetchall()
    cur.close()
    db.close()
    return render_template("house.html", house=house, threads=threads)

@app.route("/house/<int:house_id>/thread/new", methods=["GET", "POST"])
def new_thread(house_id):
    if request.method == "POST":
        title = request.form["title"]
        nickname = request.form["nickname"]
        tripcode = request.form["tripcode"]
        content = request.form["content"]
        trip_hash = hash_tripcode(tripcode)

        db = get_db()
        cur = db.cursor()

        if USE_POSTGRES:
            cur.execute(
                "INSERT INTO threads (house_id, title) VALUES (%s, %s) RETURNING id",
                (house_id, title)
            )
            thread_id = cur.fetchone()[0]
            cur.execute(
                "INSERT INTO posts (thread_id, nickname, tripcode_hash, content) VALUES (%s, %s, %s, %s)",
                (thread_id, nickname, trip_hash, content)
            )
        else:
            cur.execute(
                "INSERT INTO threads (house_id, title) VALUES (?, ?)",
                (house_id, title)
            )
            thread_id = cur.lastrowid
            cur.execute(
                "INSERT INTO posts (thread_id, nickname, tripcode_hash, content) VALUES (?, ?, ?, ?)",
                (thread_id, nickname, trip_hash, content)
            )

        db.commit()
        cur.close()
        db.close()
        return redirect(f"/thread/{thread_id}")

    return render_template("new_thread.html", house_id=house_id)

@app.route("/thread/<int:thread_id>")
def thread(thread_id):
    db = get_db()
    cur = cursor(db)
    q = "%s" if USE_POSTGRES else "?"

    cur.execute(f"SELECT * FROM threads WHERE id={q}", (thread_id,))
    thread = cur.fetchone()

    cur.execute(f"SELECT * FROM posts WHERE thread_id={q} ORDER BY id ASC", (thread_id,))
    posts_rows = cur.fetchall()

    posts = []
    for p in posts_rows:
        post = dict(p)
        cur.execute(f"SELECT * FROM replies WHERE post_id={q} ORDER BY id ASC", (p["id"],))
        post["replies"] = cur.fetchall()
        posts.append(post)

    cur.close()
    db.close()
    return render_template("thread.html", thread=thread, posts=posts)

@app.route("/post/<int:post_id>/reply", methods=["POST"])
def reply(post_id):
    nickname = request.form["nickname"]
    tripcode = request.form["tripcode"]
    content = request.form["content"]
    trip_hash = hash_tripcode(tripcode)

    db = get_db()
    cur = db.cursor()
    q = "%s" if USE_POSTGRES else "?"

    cur.execute(
        f"INSERT INTO replies (post_id, nickname, tripcode_hash, content) VALUES ({q}, {q}, {q}, {q})",
        (post_id, nickname, trip_hash, content)
    )
    db.commit()

    cur.execute(f"SELECT thread_id FROM posts WHERE id={q}", (post_id,))
    thread_id = cur.fetchone()[0]

    cur.close()
    db.close()
    return redirect(f"/thread/{thread_id}")

if __name__ == "__main__":
    app.run(debug=True)
