from flask import Flask, render_template, request, redirect, session, url_for, send_from_directory
import sqlite3
import os
from datetime import datetime
from pyngrok import ngrok
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

app = Flask(__name__)
app.secret_key = "your_secret_key"
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

# ✅ 判斷副檔名
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# ✅ 初始化資料庫
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
                image_path TEXT
            )
        ''')



# ✅ 首頁（留言區）
@app.route("/", methods=["GET", "POST"])
def index():
    if "user" not in session:
        return redirect("/login")

    if request.method == "POST":
        user = session["user"]
        content = request.form["content"].strip()[:500]
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        image_path = None

        if 'image' in request.files:
            file = request.files['image']
            if file and allowed_file(file.filename):
                filename = secure_filename(f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{file.filename}")
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                image_path = filename

        with sqlite3.connect("bbs.db") as conn:
            conn.execute("INSERT INTO posts (user, content, timestamp, image_path) VALUES (?, ?, ?, ?)",
                         (user, content, timestamp, image_path))
        return redirect("/")

    with sqlite3.connect("bbs.db") as conn:
        posts = conn.execute("SELECT * FROM posts ORDER BY id DESC").fetchall()
    return render_template("index.html", posts=posts, user=session["user"])

@app.route("/posts")
def post_list():
    if "user" not in session:
        return ""
    with sqlite3.connect("bbs.db") as conn:
        posts = conn.execute("SELECT * FROM posts ORDER BY id DESC").fetchall()
    return render_template("_post_list.html", posts=posts, user=session["user"])

# ✅ 提供圖片存取路由
@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

# ✅ 註冊頁面
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
            return "❌ 使用者名稱已存在，請重新輸入。"
    return render_template("register.html")

# ✅ 登入頁面
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
        return "❌ 登入失敗，請檢查帳號密碼。"
    return render_template("login.html")

# ✅ 登出
@app.route("/logout")
def logout():
    session.pop("user", None)
    return redirect("/login")

# ✅ 編輯留言
@app.route("/edit/<int:post_id>", methods=["GET", "POST"])
def edit(post_id):
    if "user" not in session:
        return redirect("/login")

    with sqlite3.connect("bbs.db") as conn:
        post = conn.execute("SELECT * FROM posts WHERE id = ?", (post_id,)).fetchone()

    if not post or post[1] != session["user"]:
        return "❌ 沒有權限編輯這則留言。"

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
            return "❌ 沒有權限刪除這則留言。"

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
        print(f"❌ 無法啟動 Ngrok：{e}")
    app.run(host="0.0.0.0", port=5000, debug=False)