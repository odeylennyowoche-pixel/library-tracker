# Library Management System

A web app for running a small library: manage books, register members, issue and return books, and calculate late fines automatically. Built with Python (Flask), SQLite and HTML/CSS.

## Features
- Login with two roles: admin (librarian) and member. Passwords are hashed.
- Admin: add, edit, delete and search books; register members; issue books with a due date; mark books returned.
- Due date defaults to 14 days and can be changed when issuing.
- Automatic fines: ₦50 for each day a book is late.
- Rules: no issue when no copies are available, 3 books per member, no duplicate copy per member.
- Dashboard with total books, active loans, overdue books and fines owed.
- Members can view their own loans and change their password.

## Run locally
```
git clone https://github.com/odeylennyowoche-pixel/library-tracker.git
cd library-tracker
py -m venv venv
venv\Scripts\activate
py -m pip install -r requirements.txt
py app.py
```
Then open http://127.0.0.1:5000

## Demo accounts
| Role | Username | Password |
| --- | --- | --- |
| Admin | admin | admin123 |
| Member | member | member123 |

These are for demonstration only. Change them before using the app for real.

## Notes
This is a development project. Set a `SECRET_KEY` environment variable before hosting it anywhere.