from flask import Flask, render_template, request, redirect, url_for, session, flash
import sqlite3
import os
from datetime import datetime
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)

app.secret_key = "campusfind-secret-key-change-this-later"

# ==========================================
# FILE UPLOAD CONFIGURATION
# ==========================================

UPLOAD_FOLDER = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "static",
    "uploads"
)

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

ALLOWED_EXTENSIONS = {
    "png",
    "jpg",
    "jpeg",
    "gif",
    "webp"
}

os.makedirs(UPLOAD_FOLDER, exist_ok=True)


def allowed_file(filename):
    return (
        "." in filename
        and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS
    )


# ==========================================
# DATABASE CONNECTION
# ==========================================

def get_db_connection():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    db_path = os.path.join(base_dir, "lost_found.db")

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    return conn


# ==========================================
# INITIALIZE DATABASE
# ==========================================

def init_db():
    conn = get_db_connection()

    conn.execute("""
        CREATE TABLE IF NOT EXISTS items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            type TEXT NOT NULL,
            item_name TEXT NOT NULL,
            category TEXT NOT NULL,
            description TEXT NOT NULL,
            location TEXT NOT NULL,
            date TEXT NOT NULL,
            contact TEXT NOT NULL,
            photo TEXT,
            status TEXT DEFAULT 'active',
            owner_id INTEGER,
            received_by_srn TEXT,
            received_by_name TEXT,
            received_location TEXT,
            received_at TEXT
        )
    """)

    # Add columns if updating an existing database table.
    for column_name, column_type in [
        ("received_by_srn", "TEXT"),
        ("received_by_name", "TEXT"),
        ("received_location", "TEXT"),
        ("received_at", "TEXT"),
        ("owner_id", "INTEGER"),
    ]:
        try:
            conn.execute(
                f"ALTER TABLE items ADD COLUMN {column_name} {column_type}"
            )
        except sqlite3.OperationalError:
            pass

    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL
        )
    """)

    conn.commit()
    conn.close()

init_db()

# ==========================================
# REGISTER
# ==========================================

@app.route("/register", methods=["GET", "POST"])
def register():

    if request.method == "POST":

        username = request.form["username"].strip()
        password = request.form["password"]

        if not username or not password:
            flash("Username and password are required.")
            return redirect(url_for("register"))

        hashed_password = generate_password_hash(password)

        conn = get_db_connection()

        try:
            conn.execute(
                """
                INSERT INTO users (username, password)
                VALUES (?, ?)
                """,
                (username, hashed_password)
            )

            conn.commit()

        except sqlite3.IntegrityError:
            conn.close()
            flash("Username already exists.")
            return redirect(url_for("register"))

        conn.close()

        flash("Registration successful. Please log in.")
        return redirect(url_for("login"))

    return render_template("register.html")

# ==========================================
# LOGIN
# ==========================================

@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        username = request.form["username"].strip()
        password = request.form["password"]

        conn = get_db_connection()

        user = conn.execute(
            """
            SELECT *
            FROM users
            WHERE username = ?
            """,
            (username,)
        ).fetchone()

        conn.close()

        if user and check_password_hash(user["password"], password):

            session["user_id"] = user["id"]
            session["username"] = user["username"]

            return redirect(url_for("home"))

        flash("Invalid username or password.")

    return render_template("login.html")

# ==========================================
# LOGOUT
# ==========================================

@app.route("/logout")
def logout():

    session.clear()

    return redirect(url_for("home"))


# ==========================================
# HOME PAGE
# ==========================================

@app.route("/")
def home():

    search = request.args.get("search", "").strip()
    item_type = request.args.get("type", "").strip()
    category = request.args.get("category", "").strip()

    conn = get_db_connection()

    query = """
        SELECT *
        FROM items
        WHERE status != 'deleted'
    """

    parameters = []

    # Search
    if search:
        query += """
            AND (
                item_name LIKE ?
                OR description LIKE ?
                OR location LIKE ?
            )
        """

        search_value = f"%{search}%"

        parameters.extend([
            search_value,
            search_value,
            search_value
        ])

    # Lost / Found filter
    if item_type in ["lost", "found"]:
        query += " AND type = ?"
        parameters.append(item_type)

    # Category filter
    if category:
        query += " AND category = ?"
        parameters.append(category)

    query += " ORDER BY id DESC"

    items = conn.execute(
        query,
        parameters
    ).fetchall()

    conn.close()

    return render_template(
        "index.html",
        items=items,
        search=search,
        item_type=item_type,
        category=category
    )


# ==========================================
# POST ITEM
# ==========================================

@app.route("/post", methods=["GET", "POST"])
def post_item():

    if "user_id" not in session:
        flash("Please login to post an item.")
        return redirect(url_for("login"))

    if request.method == "POST":
        item_type = request.form["type"]
        item_name = request.form["item_name"]
        category = request.form["category"]
        description = request.form["description"]
        location = request.form["location"]
        date = request.form["date"]
        contact = request.form["contact"]

        # Handle uploaded photo
        photo = request.files.get("photo")
        filename = None

        if (
            photo
            and photo.filename
            and allowed_file(photo.filename)
        ):

            filename = secure_filename(photo.filename)

            photo_path = os.path.join(
                app.config["UPLOAD_FOLDER"],
                filename
            )

            photo.save(photo_path)

        # Save item in database
        conn = get_db_connection()

        conn.execute(
            """
            INSERT INTO items
(
    type,
    item_name,
    category,
    description,
    location,
    date,
    contact,
    photo,
    owner_id
)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
    item_type,
    item_name,
    category,
    description,
    location,
    date,
    contact,
    filename,
    session["user_id"]
)
        )

        conn.commit()
        conn.close()

        return redirect(url_for("home"))

    return render_template("post.html")


# ==========================================
# ITEM DETAILS
# ==========================================

@app.route("/item/<int:item_id>")
def item_details(item_id):

    conn = get_db_connection()

    item = conn.execute(
        """
        SELECT *
        FROM items
        WHERE id = ?
        """,
        (item_id,)
    ).fetchone()

    conn.close()

    if item is None:
        return "Item not found", 404

    return render_template(
        "item.html",
        item=item
    )


# ==========================================
# EDIT ITEM
# ==========================================

@app.route("/item/<int:item_id>/edit", methods=["GET", "POST"])
def edit_item(item_id):

    # User must be logged in
    if session.get("user_id") is None:
        flash("Please login to edit an item.")
        return redirect(url_for("login"))

    conn = get_db_connection()

    item = conn.execute(
        """
        SELECT *
        FROM items
        WHERE id = ?
        """,
        (item_id,)
    ).fetchone()

    if item is None:
        conn.close()
        return "Item not found", 404

    # Only the owner can edit
    if item["owner_id"] != session.get("user_id"):
        conn.close()
        return "You are not allowed to edit this item.", 403
    # Update item
    if request.method == "POST":

        item_type = request.form["type"]
        item_name = request.form["item_name"]
        category = request.form["category"]
        description = request.form["description"]
        location = request.form["location"]
        date = request.form["date"]
        contact = request.form["contact"]

        conn.execute(
            """
            UPDATE items
            SET
                type = ?,
                item_name = ?,
                category = ?,
                description = ?,
                location = ?,
                date = ?,
                contact = ?
            WHERE id = ?
            """,
            (
                item_type,
                item_name,
                category,
                description,
                location,
                date,
                contact,
                item_id
            )
        )

        conn.commit()
        conn.close()

        return redirect(
            url_for(
                "item_details",
                item_id=item_id
            )
        )

    conn.close()

    return render_template(
        "edit.html",
        item=item
    )


# ==========================================
# MARK ITEM AS RETURNED
# ==========================================

@app.route("/item/<int:item_id>/returned", methods=["POST"])
def mark_returned(item_id):
    conn = get_db_connection()
    
    received_by_srn = request.form.get("received_by_srn", "").strip().upper()
    received_by_name = request.form.get("received_by_name", "").strip()
    received_location = request.form.get("received_location", "").strip()
    received_at = request.form.get("received_at", "").strip()

    if not received_at:
        received_at = datetime.now().strftime("%Y-%m-%d %H:%M")

    conn.execute("""
        UPDATE items 
        SET status = 'returned',
            received_by_srn = ?,
            received_by_name = ?,
            received_location = ?,
            received_at = ?
        WHERE id = ?
    """, (received_by_srn, received_by_name, received_location, received_at, item_id))
    
    conn.commit()
    conn.close()
    return redirect(url_for("item_details", item_id=item_id))

# ==========================================
# DELETE ITEM
# ==========================================

@app.route(
    "/item/<int:item_id>/delete",
    methods=["POST"]
)
def delete_item(item_id):

    if "user_id" not in session:
        flash("Please login to delete an item.")
        return redirect(url_for("login"))

    conn = get_db_connection()

    item = conn.execute(
        """
        SELECT *
        FROM items
        WHERE id = ?
        """,
        (item_id,)
    ).fetchone()

    if item is None:
        conn.close()
        return "Item not found", 404

    if item["owner_id"] != session["user_id"]:
        conn.close()
        return "You are not allowed to delete this item.", 403

    photo_filename = item["photo"]
    if photo_filename:
        photo_path = os.path.join(app.config["UPLOAD_FOLDER"], photo_filename)
        if os.path.exists(photo_path):
            try:
                os.remove(photo_path)
            except OSError:
                pass

    conn.execute(
        """
        UPDATE items
        SET status = 'deleted', photo = NULL
        WHERE id = ?
        """,
        (item_id,)
    )
    conn.commit()
    conn.close()

    flash("Item deleted successfully.")
    return redirect(url_for("home"))


# ==========================================
# START FLASK SERVER
# ==========================================

if __name__ == "__main__":
    init_db()
    app.run(debug=True)

