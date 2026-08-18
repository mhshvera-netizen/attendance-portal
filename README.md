# 🎓 JNTUACEA Attendance — Student Academic Record Book

Built exactly like the popular JNTUA student attendance app:

1. **Login with your own official portal credentials** (roll number + password)
2. We log into `jntuaceastudents.classattendance.in` for you
3. **Dashboard** shows: your NAME (big), roll number, class, academic year,
   **overall attendance %**, total classes / present / absent, and
   **subject-wise cards** — each with its %, progress colour, total / present /
   absent, **Can Skip / Need to Attend** (75% rule) and date-wise details.

Your password is used in memory only, never stored.

---

## 🔑 Logins

| Who | Username | Password |
|---|---|---|
| Student | Roll Number, e.g. `23001A0204` | Your **official portal** password (DOB etc.) |
| Admin | `admin` | `admin123` (change it) |

> If the official portal is showing its CAPTCHA (human verification), any
> automated app — including the reference student app — cannot log in until
> the portal disables it again. The app shows a clear message in that case.

## 🛠 Admin panel (`/admin`)

- Bulk import students (CSV: `roll,name,branch,year,section,dob`)
- Mark attendance per subject + date (Present/Absent)
- Consolidated reports + CSV download

## ▶️ Run

```bash
pip install -r requirements.txt
python3 app.py          # http://localhost:8000
```

Deploys on Render (Start Command: `python app.py`, Build: `pip install -r requirements.txt`)
and on PythonAnywhere via `wsgi_application` in `app.py`.

## 📁 Files

- `app.py` — the whole website (student + admin)
- `scraper.py` — official portal integration (login, details, subjects, attendance)
- `static/logo.png` — college emblem
- `requirements.txt` — `requests`, `beautifulsoup4`
