from flask import Flask, render_template, request, redirect, session, url_for, send_from_directory
import sqlite3
import os
from datetime import datetime
from pyngrok import ngrok
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from markupsafe import Markup
from datetime import datetime, timedelta

UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

app = Flask(__name__)
app.secret_key = "your_secret_key"
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def time_since(timestamp_str):
    now = datetime.now()
    timestamp = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M")
    diff = now - timestamp

    if diff < timedelta(minutes=1):
        return "剛剛"
    elif diff < timedelta(hours=1):
        return f"{diff.seconds // 60} 分鐘前"
    elif diff < timedelta(days=1):
        return f"{diff.seconds // 3600} 小時前"
    elif diff < timedelta(days=7):
        return f"{diff.days} 天前"
    else:
        return timestamp.strftime("%Y-%m-%d")

def init_db():
    with sqlite3.connect("bbs.db") as conn:
        c = conn.cursor()
        c.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE,
                password TEXT
            )
        ''')
        c.execute('''
            CREATE TABLE IF NOT EXISTS posts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user TEXT,
                content TEXT,
                timestamp TEXT,
                image_path TEXT,
                parent_id INTEGER
            )
        ''')

@app.template_filter('nl2br')
def nl2br_filter(s):
    if not s:
        return ''
    return Markup(s.replace('\n', '<br>'))

@app.route("/", methods=["GET", "POST"])
def index():
    if "user" not in session:
        return redirect("/login")

    if request.method == "POST":
        user = session["user"]
        content = request.form["content"].strip()[:500]
        parent_id = request.form.get("parent_id")
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        image_path = None

        file = request.files.get("image")
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)
            image_path = filename

        if content.strip():
            with sqlite3.connect("bbs.db") as conn:
                conn.execute("""
                    INSERT INTO posts (user, content, timestamp, image_path, parent_id)
                    VALUES (?, ?, ?, ?, ?)
                """, (user, content, timestamp, image_path, parent_id))
        return redirect("/")

    with sqlite3.connect("bbs.db") as conn:
        posts = conn.execute("SELECT * FROM posts ORDER BY id DESC").fetchall()

    post_dict = {}
    for post in posts:
        post_id = post[0]
        post_dict[post_id] = dict(
            id=post[0], user=post[1], content=post[2], timestamp=post[3],
            image=post[4], parent_id=post[5], replies=[],
            time_ago=time_since(post[3])
        )

    root_posts = []
    for post in post_dict.values():
        parent_id = post["parent_id"]
        if parent_id and parent_id in post_dict:
            post_dict[parent_id]["replies"].append(post)
        else:
            root_posts.append(post)

    for post in post_dict.values():
        post["replies"].sort(key=lambda x: x["id"], reverse=True)

    return render_template("index.html", posts=root_posts, user=session["user"])


@app.route("/posts")
def post_list():
    if "user" not in session:
        return ""
    with sqlite3.connect("bbs.db") as conn:
        posts = conn.execute("SELECT * FROM posts ORDER BY id DESC").fetchall()

    post_dict = {}
    for post in posts:
        post_id = post[0]
        post_dict[post_id] = dict(
            id=post[0], user=post[1], content=post[2],
            timestamp=post[3], image=post[4],
            parent_id=post[5], replies=[]
        )

    root_posts = []
    for post in post_dict.values():
        parent_id = post["parent_id"]
        if parent_id and parent_id in post_dict:
            post_dict[parent_id]["replies"].append(post)
        else:
            root_posts.append(post)

    for post in post_dict.values():
        post["replies"].sort(key=lambda x: x["id"], reverse=True)

    return render_template("_post_list.html", posts=root_posts, user=session["user"])


@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form["username"].strip()
        password = generate_password_hash(request.form["password"].strip())
        try:
            with sqlite3.connect("bbs.db") as conn:
                conn.execute("INSERT INTO users (username, password) VALUES (?, ?)", (username, password))
            return redirect("/login")
        except sqlite3.IntegrityError:
            return "使用者名稱已有人使用，請重新輸入"
    return render_template("register.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"].strip()
        password = request.form["password"].strip()
        with sqlite3.connect("bbs.db") as conn:
            row = conn.execute("SELECT password FROM users WHERE username = ?", (username,)).fetchone()
            if row and check_password_hash(row[0], password):
                session["user"] = username
                return redirect("/")
        return "登入失敗，請檢查帳號密碼。"
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.pop("user", None)
    return redirect("/login")

@app.route("/edit/<int:post_id>", methods=["GET", "POST"])
def edit(post_id):
    if "user" not in session:
        return redirect("/login")

    with sqlite3.connect("bbs.db") as conn:
        post = conn.execute("SELECT * FROM posts WHERE id = ?", (post_id,)).fetchone()

    if not post or post[1] != session["user"]:
        return "You have no authority to edit this comment."

    if request.method == "POST":
        new_content = request.form["content"].strip()[:500]
        with sqlite3.connect("bbs.db") as conn:
            conn.execute("UPDATE posts SET content = ? WHERE id = ?", (new_content, post_id))
        return redirect("/")

    return render_template("edit.html", post=post)

@app.route("/delete/<int:post_id>")
def delete(post_id):
    if "user" not in session:
        return redirect("/login")

    with sqlite3.connect("bbs.db") as conn:
        post = conn.execute("SELECT * FROM posts WHERE id = ?", (post_id,)).fetchone()

        if not post or post[1] != session["user"]:
            return "You have no authority to delete this comment."

        if post[4]:
            image_path = os.path.join(app.config['UPLOAD_FOLDER'], post[4])
            if os.path.exists(image_path):
                os.remove(image_path)

        conn.execute("DELETE FROM posts WHERE id = ?", (post_id,))
    return redirect("/")

if __name__ == "__main__":
    init_db()
    os.system("taskkill /F /IM ngrok.exe >nul 2>&1")
    try:
        url = ngrok.connect(5000)
        print(f"\U0001f310 Ngrok 網址：{url}")
    except Exception as e:
        print(f"Ngrok initailize failed：{e}")
    app.run(host="0.0.0.0", port=5000, debug=False)
