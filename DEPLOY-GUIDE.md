# 🚀 Permanent Link — Deploy Guide (Telugu-mix, super simple)

> Current chat link temporary untundi (nidra lo aagipothundi).
> **Permanent link kavali ante — ee 10 minute process ONCE cheyandi.**
> Then your website stays online 24x7 at a fixed link like
> `yourname.pythonanywhere.com` — Error 1033 malli raadu.

---

## ✅ Option 1 — PythonAnywhere (EASIEST, GitHub avasaram ledu)

1. Go to [pythonanywhere.com](https://www.pythonanywhere.com) → **Create a Beginner account** (free, email tho ne)
2. Login → open **Files** tab
3. Upload these files to your home folder:
   - `app.py`
   - `pythonanywhere_wsgi.py`
   - Create a folder `static` → upload `logo.png` inside it
4. Open **Web** tab → **Add a new web app** → Next → **Manual configuration** → pick **Python 3.10**
5. Scroll down to the **WSGI configuration file** link → click it → delete everything inside and paste:

```python
import sys
path = '/home/YOUR_USERNAME'   # ← change to your username
if path not in sys.path:
    sys.path.insert(0, path)

from app import wsgi_application as application
```

6. Click **Save** → go back to Web tab → click the big green **Reload** button
7. Done! Your permanent link: `https://YOUR_USERNAME.pythonanywhere.com` 🎉
   - Admin login: `admin` / `admin123` (change it first!)
   - Students login with roll number / roll number

> PythonAnywhere free account: site always on, ~3 months ki oka sari "renew"
> button click cheyali (email vastundi). App files upload cheste chalu —
> database automatic ga create avthundi.

---

## ✅ Option 2 — Render (needs a free GitHub account)

1. Create a free GitHub account → **New repository** → upload these files:
   `app.py`, `static/logo.png` (app.py ni repo root lo pettali)
2. Go to [render.com](https://render.com) → sign in with GitHub
3. **New → Web Service** → select your repository
4. Settings: Start Command = `python app.py` → Free plan → **Deploy**
5. Link: `https://your-app.onrender.com` — permanent ✅
   (Note: free Render apps sleep after 15 min idle; first visit takes ~30 sec to wake)

---

## ✅ Option 3 — Glitch (drag & drop, no GitHub)

1. [glitch.com](https://glitch.com) → sign up → **New project → hello-express**
2. Delete the example files, drag-drop `app.py` + `static/logo.png` into the editor
3. Edit `package.json` → set `"start": "python3 app.py"`
4. Open **Share → Live site** — that's your permanent link ✅

---

## 📁 Which files do I need?

All inside the `attendance/` folder in this chat workspace:

| File | Purpose |
|---|---|
| `app.py` | The whole website (works as normal server AND on PythonAnywhere WSGI) |
| `static/logo.png` | College logo |
| `pythonanywhere_wsgi.py` | WSGI config template (Option 1 only) |
| `attendance.db` | Your current data (copy it to the host to keep demo data) |

> Zip file `jntuacea-attendance-portal.zip` has everything.
