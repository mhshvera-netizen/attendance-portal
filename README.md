# 🎓 JNTUACEA — Student Academic Record Book (Online Attendance Portal)

A complete college attendance website (like the official JNTUACEA portal) —
students log in and see their **subject-wise attendance percentage**, and the
admin marks attendance class by class. Everything is stored in one small
database file, so it is shared online between all users.

---

## 🔑 Logins (defaults)

| Who | Username | Password |
|---|---|---|
| **Admin** | `admin` | `admin123` (change it in Admin → Settings) |
| **Student** | Roll Number, e.g. `22A51A0501` | Same as Roll Number (student can change it after login) |

> Demo data is pre-loaded: 44 students (CSE / ECE, I & II year), 13 subjects
> and ~2 months of attendance so you can explore everything immediately.
> Erase it anytime from **Admin → Settings → Erase All Demo Data**.

---

## ✨ Features

**Admin panel**
- Mark attendance per subject + date: Present / Absent with "All Present" quick buttons
- Add students one by one or **bulk import via CSV** (`roll,name,branch,year,section`)
- Manage subjects (code, name, branch, year, section)
- Consolidated reports with filters + **CSV download** (for defaulter lists in Excel)
- Students below 75% alert list on the admin home page
- **Self-Mark windows**: open attendance for a subject/date so students can
  mark themselves present (optionally with a closing time)
- Change admin password, reset demo data

**Student portal**
- Dashboard: overall %, today's classes, subject-wise % rings
- Full attendance history with month/subject filters + printable statement
- Self-mark button when the admin opens a window
- Change password

---

## ▶️ Run it yourself

Only Python 3 is needed (no installs, no internet):

```bash
cd attendance
python3 app.py
```

Open http://localhost:8000 — the database file `attendance.db` is created
and seeded automatically on first run.

---

## 🌍 Put it online so all students can use it

The app is a single Python file — it runs on any free Python host:

1. **Render.com** (free) — create a "Web Service", set
   Start Command: `python app.py`. Your students get a public link like
   `https://yourcollege.onrender.com`.
2. **PythonAnywhere** (free) — upload `app.py`, create a web app, point it to
   the file. Free accounts get a `username.pythonanywhere.com` link.
3. **Railway / Render / any VPS** — same command.

For a real college deployment, you can later buy a custom domain
(e.g. `attendance.yourcollege.edu.in`) and point it at the app.

### ⚠️ Notes before going live with real students
- Change the **admin password** first.
- Tell students their first password is their **roll number** and to change it.
- Keep a backup of `attendance.db` regularly (it holds all the data).
- On a public host, serve over HTTPS (Render/PythonAnywhere do this automatically).

---

## 📁 Files

```
attendance/
├── app.py           # the whole website (Python standard library only)
├── attendance.db    # database (auto-created; delete it to reset)
├── static/logo.png  # college emblem (replace with your own college logo)
├── test_all.sh      # quick regression test script (optional)
└── README.md
```
