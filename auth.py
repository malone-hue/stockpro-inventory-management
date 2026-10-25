import os
from functools import wraps

import mysql.connector
from flask import (
    Blueprint,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    session
)
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv

load_dotenv()

auth = Blueprint("auth", __name__)


def get_db_connection():
    return mysql.connector.connect(
        host=os.getenv("DB_HOST"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        database=os.getenv("DB_NAME")
    )


def login_required(view):
    @wraps(view)
    def wrapped_view(*args, **kwargs):
        if "user_id" not in session:
            flash("Please log in to access that page.", "warning")
            return redirect(url_for("auth.login"))

        return view(*args, **kwargs)

    return wrapped_view


def admin_required(view):
    @wraps(view)
    def wrapped_view(*args, **kwargs):
        if "user_id" not in session:
            flash("Please log in first.", "warning")
            return redirect(url_for("auth.login"))

        if session.get("user_role") != "admin":
            flash("You need administrator permission to access that page.", "danger")
            return redirect(url_for("home"))

        return view(*args, **kwargs)

    return wrapped_view


@auth.route("/register", methods=["GET", "POST"])
def register():
    connection = None
    cursor = None

    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)

        cursor.execute("SELECT COUNT(*) AS total FROM users")
        total_users = cursor.fetchone()["total"]

        # Registration is only available until the first account is created.
        if total_users > 0:
            flash("Registration is closed. Ask your administrator for an account.", "warning")
            return redirect(url_for("auth.login"))

        if request.method == "POST":
            full_name = request.form.get("full_name", "").strip()
            email = request.form.get("email", "").strip().lower()
            password = request.form.get("password", "")
            confirm_password = request.form.get("confirm_password", "")

            if not full_name or not email or not password or not confirm_password:
                flash("Please fill in all fields.", "danger")

            elif password != confirm_password:
                flash("The passwords do not match.", "danger")

            elif len(password) < 10:
                flash("Your password must contain at least 10 characters.", "danger")

            else:
                password_hash = generate_password_hash(password)

                cursor.execute(
                    """
                    INSERT INTO users (full_name, email, password_hash, role)
                    VALUES (%s, %s, %s, 'admin')
                    """,
                    (full_name, email, password_hash)
                )
                connection.commit()

                flash("Administrator account created. You can now log in.", "success")
                return redirect(url_for("auth.login"))

        return render_template("register.html")

    except mysql.connector.Error:
        if connection and connection.is_connected():
            connection.rollback()

        flash("A database error occurred. Please try again.", "danger")
        return redirect(url_for("auth.login"))

    finally:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()


@auth.route("/login", methods=["GET", "POST"])
def login():
    if session.get("user_id"):
        return redirect(url_for("home"))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        connection = None
        cursor = None

        try:
            connection = get_db_connection()
            cursor = connection.cursor(dictionary=True)

            cursor.execute(
                """
                SELECT id, full_name, email, password_hash, role
                FROM users
                WHERE email = %s
                """,
                (email,)
            )
            user = cursor.fetchone()

            if user and check_password_hash(user["password_hash"], password):
                session.clear()
                session["user_id"] = user["id"]
                session["user_name"] = user["full_name"]
                session["user_role"] = user["role"]

                flash("Login successful. Welcome back!", "success")
                return redirect(url_for("home"))

            flash("Invalid email or password.", "danger")

        except mysql.connector.Error:
            flash("Unable to connect to the database. Please try again.", "danger")

        finally:
            if cursor:
                cursor.close()
            if connection and connection.is_connected():
                connection.close()

    return render_template("login.html")


@auth.route("/logout", methods=["POST"])
def logout():
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for("auth.login"))
@auth.route("/users", methods=["GET", "POST"])
@login_required
def users():
    if session.get("user_role") != "admin":
        flash("Only administrators can manage users.", "danger")
        return redirect(url_for("home"))

    connection = None
    cursor = None

    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)

        if request.method == "POST":
            full_name = request.form.get("full_name", "").strip()
            email = request.form.get("email", "").strip().lower()
            password = request.form.get("password", "")
            role = request.form.get("role", "staff")

            if not full_name or not email or not password:
                flash("Please fill in all required fields.", "danger")

            elif len(password) < 10:
                flash("Password must contain at least 10 characters.", "danger")

            elif role not in ("admin", "staff"):
                flash("Invalid user role.", "danger")

            else:
                password_hash = generate_password_hash(password)

                cursor.execute(
                    """
                    INSERT INTO users
                        (full_name, email, password_hash, role)
                    VALUES (%s, %s, %s, %s)
                    """,
                    (full_name, email, password_hash, role)
                )

                connection.commit()
                flash("User account created successfully.", "success")
                return redirect(url_for("auth.users"))

        cursor.execute(
            """
            SELECT id, full_name, email, role, created_at
            FROM users
            ORDER BY id DESC
            """
        )

        users_list = cursor.fetchall()

        return render_template(
            "users.html",
            users=users_list
        )

    except mysql.connector.IntegrityError:
        if connection and connection.is_connected():
            connection.rollback()

        flash("That email address is already registered.", "danger")
        return redirect(url_for("auth.users"))

    except mysql.connector.Error:
        if connection and connection.is_connected():
            connection.rollback()

        flash("A database error occurred.", "danger")
        return redirect(url_for("home"))

    finally:
        if cursor:
            cursor.close()

        if connection and connection.is_connected():
            connection.close()

@auth.route("/users/edit/<int:user_id>", methods=["GET", "POST"])
@login_required
def edit_user(user_id):
    if session.get("user_role") != "admin":
        flash("Only administrators can manage users.", "danger")
        return redirect(url_for("home"))

    connection = None
    cursor = None

    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)

        if request.method == "POST":
            full_name = request.form.get("full_name", "").strip()
            email = request.form.get("email", "").strip().lower()
            role = request.form.get("role", "")

            if not full_name or not email:
                flash("Name and email are required.", "danger")
                return redirect(url_for("auth.edit_user", user_id=user_id))

            if role not in ("admin", "staff"):
                flash("Invalid user role.", "danger")
                return redirect(url_for("auth.edit_user", user_id=user_id))

            cursor.execute(
                "SELECT id FROM users WHERE id = %s",
                (user_id,)
            )

            if cursor.fetchone() is None:
                flash("User account not found.", "danger")
                return redirect(url_for("auth.users"))

            cursor.execute(
                """
                UPDATE users
                SET full_name = %s, email = %s, role = %s
                WHERE id = %s
                """,
                (full_name, email, role, user_id)
            )

            connection.commit()

            # Keep the current session consistent if the admin edits
            # their own name or role.
            if session.get("user_id") == user_id:
                session["user_name"] = full_name
                session["user_role"] = role

            flash("User details updated successfully.", "success")
            return redirect(url_for("auth.users"))

        cursor.execute(
            """
            SELECT id, full_name, email, role
            FROM users
            WHERE id = %s
            """,
            (user_id,)
        )

        user = cursor.fetchone()

        if user is None:
            flash("User account not found.", "danger")
            return redirect(url_for("auth.users"))

        return render_template("edit_user.html", user=user)

    except mysql.connector.IntegrityError:
        if connection and connection.is_connected():
            connection.rollback()

        flash("That email address is already registered.", "danger")
        return redirect(url_for("auth.edit_user", user_id=user_id))

    except mysql.connector.Error:
        if connection and connection.is_connected():
            connection.rollback()

        flash("A database error occurred.", "danger")
        return redirect(url_for("auth.users"))

    finally:
        if cursor:
            cursor.close()

        if connection and connection.is_connected():
            connection.close()

@auth.route("/users/delete/<int:user_id>", methods=["POST"])
@login_required
def delete_user(user_id):
    if session.get("user_role") != "admin":
        flash("Only administrators can manage users.", "danger")
        return redirect(url_for("home"))

    current_user_id = session.get("user_id")

    # Prevent an administrator from deleting their own account.
    if current_user_id == user_id:
        flash("You cannot delete your own account.", "danger")
        return redirect(url_for("auth.users"))

    connection = None
    cursor = None

    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)

        connection.start_transaction()

        # Lock the target account while checking it.
        cursor.execute(
            "SELECT id, full_name, role FROM users WHERE id = %s FOR UPDATE",
            (user_id,)
        )
        user = cursor.fetchone()

        if user is None:
            connection.rollback()
            flash("User account not found.", "danger")
            return redirect(url_for("auth.users"))

        # Do not allow deletion of the last administrator.
        if user["role"] == "admin":
            cursor.execute(
                "SELECT COUNT(*) AS admin_count FROM users WHERE role = 'admin'"
            )
            admin_count = cursor.fetchone()["admin_count"]

            if admin_count <= 1:
                connection.rollback()
                flash(
                    "You cannot delete the last administrator account.",
                    "danger"
                )
                return redirect(url_for("auth.users"))

        cursor.execute(
            "DELETE FROM users WHERE id = %s",
            (user_id,)
        )

        connection.commit()

        flash(
            f"User account '{user['full_name']}' was deleted successfully.",
            "success"
        )
        return redirect(url_for("auth.users"))

    except mysql.connector.Error:
        if connection and connection.is_connected():
            connection.rollback()

        app_error = "A database error occurred while deleting the user."
        flash(app_error, "danger")
        return redirect(url_for("auth.users"))

    finally:
        if cursor:
            cursor.close()

        if connection and connection.is_connected():
            connection.close()


