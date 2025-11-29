from flask import Flask, render_template, request, redirect
import sqlite3
import hashlib

app = Flask(__name__)

# --- Database setup ---
def get_db():
    conn = sqlite3.connect("database.db")
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    db = get_db()
    # houses
    db.execute("""CREATE TABLE IF NOT EXISTS houses (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE NOT NULL
                 )""")
    # threads
    db.execute("""CREATE TABLE IF NOT EXISTS threads (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    house_id INTEGER NOT NULL,
                    title TEXT NOT NULL
                 )""")
    # posts
    db.execute("""CREATE TABLE IF NOT EXISTS posts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    thread_id INTEGER NOT NULL,
                    nickname TEXT NOT NULL,
                    tripcode_hash TEXT NOT NULL,
                    content TEXT NOT NULL
                 )""")
    # replies
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

@app.route("/house/new", methods=["GET","POST"])
def new_house():
    if request.method == "POST":
        name = request.form["name"]
        db = get_db()
        try:
            db.execute("INSERT INTO houses (name) VALUES (?)", (name,))
            db.commit()
            return redirect("/")
        except sqlite3.IntegrityError:
            return "House name already taken!"
    return render_template("new_house.html")

@app.route("/house/<int:house_id>")
def house(house_id):
    db = get_db()
    house = db.execute("SELECT * FROM houses WHERE id=?", (house_id,)).fetchone()
    threads = db.execute("SELECT * FROM threads WHERE house_id=? ORDER BY id DESC", (house_id,)).fetchall()
    return render_template("house.html", house=house, threads=threads)

@app.route("/house/<int:house_id>/thread/new", methods=["GET","POST"])
def new_thread(house_id):
    if request.method == "POST":
        title = request.form["title"]
        nickname = request.form["nickname"]
        tripcode = request.form["tripcode"]
        content = request.form["content"]
        trip_hash = hash_tripcode(tripcode)

        db = get_db()
        cur = db.cursor()
        cur.execute("INSERT INTO threads (house_id, title) VALUES (?, ?)", (house_id, title))
        thread_id = cur.lastrowid
        cur.execute("INSERT INTO posts (thread_id, nickname, tripcode_hash, content) VALUES (?, ?, ?, ?)",
                    (thread_id, nickname, trip_hash, content))
        db.commit()
        return redirect(f"/thread/{thread_id}")
    return render_template("new_thread.html", house_id=house_id)

@app.route("/thread/<int:thread_id>")
def thread(thread_id):
    db = get_db()
    thread = db.execute("SELECT * FROM threads WHERE id=?", (thread_id,)).fetchone()
    posts_rows = db.execute("SELECT * FROM posts WHERE thread_id=? ORDER BY id ASC", (thread_id,)).fetchall()
    
    # convert posts to dicts and add replies
    posts = []
    for p in posts_rows:
        post = dict(p)
        post["replies"] = [dict(r) for r in db.execute("SELECT * FROM replies WHERE post_id=? ORDER BY id ASC", (p["id"],)).fetchall()]
        posts.append(post)
    
    return render_template("thread.html", thread=thread, posts=posts)

@app.route("/post/<int:post_id>/reply", methods=["POST"])
def reply(post_id):
    nickname = request.form["nickname"]
    tripcode = request.form["tripcode"]
    content = request.form["content"]
    trip_hash = hash_tripcode(tripcode)

    db = get_db()
    db.execute("INSERT INTO replies (post_id, nickname, tripcode_hash, content) VALUES (?, ?, ?, ?)",
               (post_id, nickname, trip_hash, content))
    db.commit()
    thread_id = db.execute("SELECT thread_id FROM posts WHERE id=?", (post_id,)).fetchone()["thread_id"]
    return redirect(f"/thread/{thread_id}")

if __name__ == "__main__":
    app.run(debug=True)
