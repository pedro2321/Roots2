from flask import Flask, render_template, request, redirect
import psycopg2
import psycopg2.extras
import hashlib
import html
import os

app = Flask(__name__)

# --- Database setup ---
DATABASE_URL = os.getenv("DATABASE_URL")  # Railway sets this automatically

def get_db():
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    return conn

def init_db():
    db = get_db()
    cur = db.cursor()
    
    # houses
    cur.execute("""
        CREATE TABLE IF NOT EXISTS houses (
            id SERIAL PRIMARY KEY,
            name TEXT UNIQUE NOT NULL
        )
    """)
    # threads
    cur.execute("""
        CREATE TABLE IF NOT EXISTS threads (
            id SERIAL PRIMARY KEY,
            house_id INTEGER NOT NULL REFERENCES houses(id),
            title TEXT NOT NULL
        )
    """)
    # posts
    cur.execute("""
        CREATE TABLE IF NOT EXISTS posts (
            id SERIAL PRIMARY KEY,
            thread_id INTEGER NOT NULL REFERENCES threads(id),
            nickname TEXT NOT NULL,
            tripcode_hash TEXT NOT NULL,
            content TEXT NOT NULL
        )
    """)
    # replies
    cur.execute("""
        CREATE TABLE IF NOT EXISTS replies (
            id SERIAL PRIMARY KEY,
            post_id INTEGER NOT NULL REFERENCES posts(id),
            nickname TEXT NOT NULL,
            tripcode_hash TEXT NOT NULL,
            content TEXT NOT NULL
        )
    """)

init_db()

# --- Helper for tripcode hashing ---
def hash_tripcode(trip):
    return hashlib.sha256(trip.encode()).hexdigest()

# --- Routes ---
@app.route("/")
def index():
    db = get_db()
    cur = db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT * FROM houses ORDER BY id DESC")
    houses = cur.fetchall()
    return render_template("index.html", houses=houses)

@app.route("/house/new", methods=["GET","POST"])
def new_house():
    if request.method == "POST":
        name = html.escape(request.form["name"])
        db = get_db()
        cur = db.cursor()
        try:
            cur.execute("INSERT INTO houses (name) VALUES (%s)", (name,))
            return redirect("/")
        except psycopg2.errors.UniqueViolation:
            return "House name already taken!"
    return render_template("new_house.html")

@app.route("/house/<int:house_id>")
def house(house_id):
    db = get_db()
    cur = db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT * FROM houses WHERE id=%s", (house_id,))
    house = cur.fetchone()
    cur.execute("SELECT * FROM threads WHERE house_id=%s ORDER BY id DESC", (house_id,))
    threads = cur.fetchall()
    return render_template("house.html", house=house, threads=threads)

@app.route("/house/<int:house_id>/thread/new", methods=["GET","POST"])
def new_thread(house_id):
    if request.method == "POST":
        title = html.escape(request.form["title"])
        nickname = html.escape(request.form["nickname"])
        tripcode = request.form["tripcode"]
        content = html.escape(request.form["content"])
        trip_hash = hash_tripcode(tripcode)

        db = get_db()
        cur = db.cursor()
        cur.execute("INSERT INTO threads (house_id, title) VALUES (%s, %s) RETURNING id", (house_id, title))
        thread_id = cur.fetchone()[0]
        cur.execute(
            "INSERT INTO posts (thread_id, nickname, tripcode_hash, content) VALUES (%s, %s, %s, %s)",
            (thread_id, nickname, trip_hash, content)
        )
        return redirect(f"/thread/{thread_id}")
    return render_template("new_thread.html", house_id=house_id)

@app.route("/thread/<int:thread_id>")
def thread(thread_id):
    db = get_db()
    cur = db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT * FROM threads WHERE id=%s", (thread_id,))
    thread = cur.fetchone()
    cur.execute("SELECT * FROM posts WHERE thread_id=%s ORDER BY id ASC", (thread_id,))
    posts = cur.fetchall()
    for post in posts:
        post_id = post["id"]
        cur.execute("SELECT * FROM replies WHERE post_id=%s ORDER BY id ASC", (post_id,))
        post["replies"] = cur.fetchall()
    return render_template("thread.html", thread=thread, posts=posts)

@app.route("/post/<int:post_id>/reply", methods=["POST"])
def reply(post_id):
    nickname = html.escape(request.form["nickname"])
    tripcode = request.form["tripcode"]
    content = html.escape(request.form["content"])
    trip_hash = hash_tripcode(tripcode)

    db = get_db()
    cur = db.cursor()
    cur.execute(
        "INSERT INTO replies (post_id, nickname, tripcode_hash, content) VALUES (%s, %s, %s, %s)",
        (post_id, nickname, trip_hash, content)
    )
    cur.execute("SELECT thread_id FROM posts WHERE id=%s", (post_id,))
    thread_id = cur.fetchone()[0]
    return redirect(f"/thread/{thread_id}")

if __name__ == "__main__":
    app.run(debug=True)
