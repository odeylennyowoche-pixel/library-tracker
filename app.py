from datetime import date, timedelta
from functools import wraps

from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.config["SECRET_KEY"] = "change-this-secret-key"
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///library.db"

db = SQLAlchemy(app)

LOAN_DAYS = 14        # standard loan period (default due date)
FINE_PER_DAY = 50     # fine in naira for each late day
MAX_LOANS = 3         # most books a member can hold at once
MAX_LOAN_DAYS = 90    # furthest ahead a due date can be set


# ---------------------------------------------------------------- models

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="member")  # "admin" or "member"

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class Book(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    author = db.Column(db.String(100), nullable=False)
    isbn = db.Column(db.String(20), unique=True, nullable=False)
    copies_total = db.Column(db.Integer, nullable=False, default=1)
    copies_available = db.Column(db.Integer, nullable=False, default=1)


class Loan(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    book_id = db.Column(db.Integer, db.ForeignKey("book.id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    borrowed_on = db.Column(db.Date, nullable=False, default=date.today)
    due_on = db.Column(db.Date, nullable=False)
    returned_on = db.Column(db.Date, nullable=True)
    fine = db.Column(db.Integer, nullable=False, default=0)

    book = db.relationship("Book", backref="loans")
    member = db.relationship("User", backref="loans")

    def calculate_fine(self):
        """Fine for a late book: days late x FINE_PER_DAY."""
        end = self.returned_on or date.today()
        days_late = (end - self.due_on).days
        return max(days_late, 0) * FINE_PER_DAY


def seed_data():
    """Add two starter accounts and a few books, only if the database is empty."""
    if User.query.first() is None:
        admin = User(username="admin", role="admin")
        admin.set_password("admin123")
        member = User(username="member", role="member")
        member.set_password("member123")
        db.session.add_all([admin, member])

    if Book.query.first() is None:
        db.session.add_all([
            Book(title="Things Fall Apart", author="Chinua Achebe",
                 isbn="9780385474542", copies_total=3, copies_available=3),
            Book(title="Half of a Yellow Sun", author="Chimamanda Ngozi Adichie",
                 isbn="9781400095209", copies_total=2, copies_available=2),
            Book(title="Python Crash Course", author="Eric Matthes",
                 isbn="9781593279288", copies_total=1, copies_available=1),
        ])

    db.session.commit()


# ------------------------------------------------------- access control

def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            flash("Please log in first.")
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapped


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if session.get("role") != "admin":
            flash("Admins only. You do not have access to that page.")
            return redirect(url_for("dashboard"))
        return view(*args, **kwargs)
    return wrapped


# ----------------------------------------------------- login and pages

@app.route("/")
def home():
    if "user_id" in session:
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"].strip()
        password = request.form["password"]
        user = User.query.filter_by(username=username).first()

        if user and user.check_password(password):
            session.clear()
            session["user_id"] = user.id
            session["username"] = user.username
            session["role"] = user.role
            return redirect(url_for("dashboard"))

        flash("Wrong username or password.")

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/dashboard")
@login_required
def dashboard():
    total_books = Book.query.count()
    active_loans = Loan.query.filter_by(returned_on=None).count()
    return render_template("dashboard.html",
                           total_books=total_books,
                           active_loans=active_loans)


@app.route("/admin")
@login_required
@admin_required
def admin_area():
    return render_template("admin.html")


# ----------------------------------------------------------------- books

def read_book_form():
    """Read the book form and return (title, author, isbn, copies)."""
    title = request.form["title"].strip()
    author = request.form["author"].strip()
    isbn = request.form["isbn"].strip()
    try:
        copies = int(request.form["copies"])
    except ValueError:
        copies = 0
    return title, author, isbn, copies


@app.route("/books")
@login_required
def books():
    q = request.args.get("q", "").strip()
    query = Book.query
    if q:
        like = f"%{q}%"
        query = query.filter(
            db.or_(Book.title.ilike(like), Book.author.ilike(like), Book.isbn.ilike(like))
        )
    all_books = query.order_by(Book.title).all()
    return render_template("books.html", books=all_books, q=q)


@app.route("/books/add", methods=["GET", "POST"])
@login_required
@admin_required
def add_book():
    values = {}
    if request.method == "POST":
        title, author, isbn, copies = read_book_form()
        values = {"title": title, "author": author, "isbn": isbn, "copies": copies}

        if not title or not author or not isbn or copies < 1:
            flash("Fill in every field. Copies must be at least 1.")
        elif Book.query.filter_by(isbn=isbn).first():
            flash("A book with that ISBN already exists.")
        else:
            db.session.add(Book(title=title, author=author, isbn=isbn,
                                copies_total=copies, copies_available=copies))
            db.session.commit()
            flash("Book added.", "success")
            return redirect(url_for("books"))

    return render_template("book_form.html", book=None, values=values)


@app.route("/books/<int:book_id>/edit", methods=["GET", "POST"])
@login_required
@admin_required
def edit_book(book_id):
    book = db.get_or_404(Book, book_id)
    values = {"title": book.title, "author": book.author,
              "isbn": book.isbn, "copies": book.copies_total}

    if request.method == "POST":
        title, author, isbn, copies = read_book_form()
        values = {"title": title, "author": author, "isbn": isbn, "copies": copies}
        borrowed = book.copies_total - book.copies_available
        other = Book.query.filter(Book.isbn == isbn, Book.id != book.id).first()

        if not title or not author or not isbn:
            flash("Fill in every field.")
        elif other:
            flash("Another book already uses that ISBN.")
        elif copies < max(borrowed, 1):
            flash(f"Total copies must be at least {max(borrowed, 1)}.")
        else:
            book.title = title
            book.author = author
            book.isbn = isbn
            book.copies_total = copies
            book.copies_available = copies - borrowed
            db.session.commit()
            flash("Book updated.", "success")
            return redirect(url_for("books"))

    return render_template("book_form.html", book=book, values=values)


@app.route("/books/<int:book_id>/delete", methods=["POST"])
@login_required
@admin_required
def delete_book(book_id):
    book = db.get_or_404(Book, book_id)
    if book.loans:
        flash("This book has loan records, so it cannot be deleted.")
    else:
        db.session.delete(book)
        db.session.commit()
        flash("Book deleted.", "success")
    return redirect(url_for("books"))


# ----------------------------------------------------------------- loans

@app.route("/loans")
@login_required
@admin_required
def loans():
    all_loans = Loan.query.all()
    # Active loans first, then by due date
    all_loans.sort(key=lambda l: (l.returned_on is not None, l.due_on))
    return render_template("loans.html", loans=all_loans, today=date.today())


@app.route("/my-loans")
@login_required
def my_loans():
    mine = Loan.query.filter_by(user_id=session["user_id"]).all()
    mine.sort(key=lambda l: (l.returned_on is not None, l.due_on))
    return render_template("my_loans.html", loans=mine, today=date.today())


@app.route("/loans/issue", methods=["GET", "POST"])
@login_required
@admin_required
def issue_book():
    members = User.query.filter_by(role="member").order_by(User.username).all()
    available = Book.query.filter(Book.copies_available > 0).order_by(Book.title).all()
    default_due = (date.today() + timedelta(days=LOAN_DAYS)).isoformat()

    if request.method == "POST":
        member_id = request.form.get("member_id", type=int)
        book_id = request.form.get("book_id", type=int)
        member = db.session.get(User, member_id) if member_id else None
        book = db.session.get(Book, book_id) if book_id else None

        due_text = request.form.get("due_on", "")
        default_due = due_text or default_due
        try:
            due_on = date.fromisoformat(due_text)
        except ValueError:
            due_on = None

        if not member or member.role != "member" or not book:
            flash("Choose a member and a book.")
        elif due_on is None:
            flash("Choose a valid due date.")
        elif due_on > date.today() + timedelta(days=MAX_LOAN_DAYS):
            flash(f"The due date cannot be more than {MAX_LOAN_DAYS} days away.")
        elif book.copies_available < 1:
            flash("No copies of that book are available.")
        else:
            active = Loan.query.filter_by(user_id=member.id, returned_on=None).all()
            if len(active) >= MAX_LOANS:
                flash(f"{member.username} already has {MAX_LOANS} books out.")
            elif any(l.book_id == book.id for l in active):
                flash(f"{member.username} already has a copy of this book.")
            else:
                loan = Loan(book_id=book.id, user_id=member.id,
                            borrowed_on=date.today(), due_on=due_on)
                book.copies_available -= 1
                db.session.add(loan)
                db.session.commit()
                flash(f"Issued '{book.title}' to {member.username}. "
                      f"Due on {loan.due_on.strftime('%d %b %Y')}.", "success")
                return redirect(url_for("loans"))

    return render_template("issue.html", members=members, books=available,
                           default_due=default_due)


@app.route("/loans/<int:loan_id>/return", methods=["POST"])
@login_required
@admin_required
def return_book(loan_id):
    loan = db.get_or_404(Loan, loan_id)
    if loan.returned_on:
        flash("That book was already returned.")
    else:
        loan.returned_on = date.today()
        loan.fine = loan.calculate_fine()
        loan.book.copies_available += 1
        db.session.commit()
        if loan.fine:
            flash(f"Returned late. Fine: ₦{loan.fine}.", "success")
        else:
            flash("Book returned on time. No fine.", "success")
    return redirect(url_for("loans"))


# --------------------------------------------------------------- members

@app.route("/members", methods=["GET", "POST"])
@login_required
@admin_required
def manage_members():
    if request.method == "POST":
        username = request.form["username"].strip()
        password = request.form["password"]

        if len(username) < 3:
            flash("Username must be at least 3 characters.")
        elif len(password) < 6:
            flash("Password must be at least 6 characters.")
        elif User.query.filter_by(username=username).first():
            flash("That username is already taken.")
        else:
            user = User(username=username, role="member")
            user.set_password(password)
            db.session.add(user)
            db.session.commit()
            flash(f"Member '{username}' created.", "success")
            return redirect(url_for("manage_members"))

    all_members = User.query.filter_by(role="member").order_by(User.username).all()
    return render_template("members.html", members=all_members)


# ------------------------------------------------------------------ run

if __name__ == "__main__":
    with app.app_context():
        db.create_all()
        seed_data()
    app.run(debug=True)