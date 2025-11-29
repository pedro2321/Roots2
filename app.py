from flask import Flask, render_template, request, redirect, url_for
import sqlite3
import hashlib
import os

app = Flask(__name__)
DB_PATH = "database.db"

# --- Database setup ---
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    if not os.path.exists(DB_PATH):
        db = get_db()
        db.execute("""CREATE TABLE IF NOT EXISTS houses (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        name TEXT UNIQUE NOT NULL
                     )""")
        db.execute("""CREATE TABLE IF NOT EXISTS threads (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        house_id INTEGER NOT NULL,
                        title TEXT NOT NULL
                     )""")
        db.execute("""CREATE TABLE IF NOT EXISTS posts (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        thread_id INTEGER NOT NULL,
                        nickname TEXT NOT NULL,
                        tripcode_hash TEXT NOT NULL,
                        content TEXT NOT NULL
                     )""")
        db.execute("""CREATE TABLE IF NOT EXISTS replies (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        post_id INTEGER NOT NULL,
                        nickname TEXT NOT NULL,
                        tripcode_hash TEXT NOT NULL,
                        content TEXT NOT NULL
                     )""")
        db.commit()

init_db()

# --- Helper for tripcode hashing ---
def hash_tripcode(trip):
    return hashlib.sha256(trip.encode()).hexdigest()

# --- Routes ---
@app.route("/")
def index():
    db = get_db()
    houses = db.execute("SELECT * FROM houses ORDER BY id DESC").fetchall()
    return render_template("index.html", houses=houses)

@app.route("/house/new", methods=["GET", "POST"])
def new_house():
    if request.method == "POST":
        name = request.form.get("name")
        if not name:
            return "Name cannot be empty", 400
        db = get_db()
        try:
            db.execute("INSERT INTO houses (name) VALUES (?)", (name,))
            db.commit()
            return redirect(url_for("index"))
        except sqlite3.IntegrityError:
            return "House name already taken!", 400
    return render_template("new_house.html")

@app.route("/house/<int:house_id>")
def house(house_id):
    db = get_db()
    house = db.execute("SELECT * FROM houses WHERE id=?", (house_id,)).fetchone()
    if not house:
        return "House not found", 404
    threads = db.execute(
        "SELECT * FROM threads WHERE house_id=? ORDER BY id DESC", (house_id,)
    ).fetchall()
    return render_template("house.html", house=house, threads=threads)

@app.route("/house/<int:house_id>/thread/new", methods=["GET", "POST"])
def new_thread(house_id):
    db = get_db()
    house = db.execute("SELECT * FROM houses WHERE id=?", (house_id,)).fetchone()
    if not house:
        return "House not found", 404
    if request.method == "POST":
        title = request.form.get("title")
        nickname = request.form.get("nickname")
        tripcode = request.form.get("tripcode", "")
        content = request.form.get("content")
        if not (title and nickname and content):
            return "Missing fields", 400
        trip_hash = hash_tripcode(tripcode)

        cur = db.cursor()
        cur.execute("INSERT INTO threads (house_id, title) VALUES (?, ?)", (house_id, title))
        thread_id = cur.lastrowid
        cur.execute(
            "INSERT INTO posts (thread_id, nickname, tripcode_hash, content) VALUES (?, ?, ?, ?)",
            (thread_id, nickname, trip_hash, content),
        )
        db.commit()
        return redirect(url_for("thread", thread_id=thread_id))
    return render_template("new_thread.html", house=house)

@app.route("/thread/<int:thread_id>")
def thread(thread_id):
    db = get_db()
    thread_row = db.execute("SELECT * FROM threads WHERE id=?", (thread_id,)).fetchone()
    if not thread_row:
        return "Thread not found", 404
    posts_rows = db.execute("SELECT * FROM posts WHERE thread_id=? ORDER BY id ASC", (thread_id,)).fetchall()

    posts = []
    for p in posts_rows:
        post = dict(p)
        post["replies"] = [
            dict(r) for r in db.execute("SELECT * FROM replies WHERE post_id=? ORDER BY id ASC", (p["id"],)).fetchall()
        ]
        posts.append(post)

    return render_template("thread.html", thread=thread_row, posts=posts)

@app.route("/post/<int:post_id>/reply", methods=["POST"])
def reply(post_id):
    nickname = request.form.get("nickname")
    tripcode = request.form.get("tripcode", "")
    content = request.form.get("content")
    if not (nickname and content):
        return "Missing fields", 400
    trip_hash = hash_tripcode(tripcode)

    db = get_db()
    db.execute("INSERT INTO replies (post_id, nickname, tripcode_hash, content) VALUES (?, ?, ?, ?)",
               (post_id, nickname, trip_hash, content))
    db.commit()
    thread_id_row = db.execute("SELECT thread_id FROM posts WHERE id=?", (post_id,)).fetchone()
    if not thread_id_row:
        return "Original post not found", 404
    return redirect(url_for("thread", thread_id=thread_id_row["thread_id"]))

if __name__ == "__main__":
    app.run(debug=True)
