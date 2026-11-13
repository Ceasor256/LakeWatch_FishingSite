# LakeWatch — Fish Landing Site Compliance & Monitoring

LakeWatch is a small website for fisheries staff at landing sites. You use it to:

- **record fish catches** as they are landed (species, site, fisher, boat, quantity and measured length),
- **automatically check each catch against a minimum legal size** that you configure for each species,
- **follow up** on undersized catches with inspection and enforcement records,
- **see reports** by species and landing site, and **export** records to a spreadsheet (CSV).

It is built with [Django](https://www.djangoproject.com/) (Python) and runs on your own computer with no extra setup, or on a server with PostgreSQL.

> ⚠️ **Compliance note.** LakeWatch does **not** come with any official legal size limits. An authorised fisheries officer must look up the current regulation and enter each species' minimum size and its source. "Meets configured size" only means the measured length was at or above the number someone typed in. It is not a legal certification. Flagged catches should always be reviewed by an authorised person.

---

## Contents

1. [Quick start (Windows)](#1-quick-start-windows)
2. [Quick start (macOS / Linux)](#2-quick-start-macos--linux)
3. [Try it with demo data](#3-try-it-with-demo-data)
4. [How to use LakeWatch](#4-how-to-use-lakewatch)
5. [Users and permissions](#5-users-and-permissions)
6. [How the size check works](#6-how-the-size-check-works)
7. [Settings (`.env` file)](#7-settings-env-file)
8. [Using PostgreSQL](#8-using-postgresql)
9. [Running the tests](#9-running-the-tests)
10. [Putting it on a server](#10-putting-it-on-a-server)
11. [Troubleshooting](#11-troubleshooting)
12. [Project structure](#12-project-structure)

---

## 1. Quick start (Windows)

You need **Python 3.10 or newer**. Check by opening PowerShell and typing `py --version`. If it isn't installed, get it from [python.org](https://www.python.org/downloads/) and tick **"Add python.exe to PATH"** during setup.

Open PowerShell **in this project folder** (in File Explorer, open the folder, click the address bar, type `powershell` and press Enter). Then run these commands one at a time:

```powershell
# 1. Create a virtual environment (skip if the "venv" folder already exists)
py -m venv venv

# 2. Turn it on. Your prompt will start with (venv)
venv\Scripts\Activate.ps1

# 3. Install the required packages
python -m pip install -r requirements.txt

# 4. Create or update the database tables
python manage.py migrate

# 5. Create your first (administrator) account. You'll be asked for a username and password
python manage.py createsuperuser

# 6. Start the website
python manage.py runserver
```

Open **http://127.0.0.1:8000/** in your browser and sign in with the account from step 5.

To stop the website press **Ctrl + C** in PowerShell. Next time, you only need steps 2 and 6 (plus step 4 if you've updated the code).

> **"running scripts is disabled on this system"?** Run this once, then try step 2 again:
> `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`

## 2. Quick start (macOS / Linux)

```bash
python3 -m venv venv
source venv/bin/activate
python -m pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Then open **http://127.0.0.1:8000/**.

## 3. Try it with demo data

Want to look around before entering real data? With the virtual environment turned on, run:

```bash
python manage.py seed_demo
```

This adds three demo landing sites, three demo species, four fishers, four boats, about two weeks of catches and a few inspections. Everything is clearly labelled **"demo"**.

- It only runs on a database with no catch records yet (use `--force` to add the data anyway).
- **The demo minimum sizes are made up.** Delete or replace them before real use.
- To start completely fresh on SQLite, stop the server, delete `db.sqlite3`, then run `migrate` and `createsuperuser` again.

## 4. How to use LakeWatch

### First-time setup (staff user)
1. **Landing sites → Add landing site.** Add every site you monitor.
2. **Fish species & limits → Add species.** For each species, enter the **minimum legal length (cm)** *and* the **legal reference** it comes from (for example the regulation name and section). If you don't have a verified limit yet, leave the minimum empty. Catches of that species will then stay *Pending review*.
3. *(Optional)* **Fishers** and **Boats.** Register them so catches can be linked to people and vessels.
4. Create accounts for other staff in **Admin & users** (see [section 5](#5-users-and-permissions)).

### Day-to-day work
| Task | Where |
|---|---|
| Record a landed catch | **Catch records → Register catch.** Use **Save & add another** to enter several in a row. |
| Find a catch | **Catch records.** Search by species, site, fisher, boat, notes or reference number (e.g. `LW-0012`), and filter by status, site, species and date. |
| Fix a mistake in a catch | Open the catch → **Edit**. The size status is re-checked automatically. |
| Follow up an undersized catch | Open the catch → **Record inspection**. The catch is filled in for you. |
| See what needs attention | **Overview.** The *Needs attention* panel lists flagged and pending catches. |
| Get numbers for a period | **Reports & analytics.** Pick a date range. |
| Export to Excel | **Export CSV** on *Catch records* (exports exactly what your filters show) or on *Reports* (exports the chosen date range). |

### What the statuses mean
| Status | Meaning |
|---|---|
| **Meets configured size** | Measured length is **at or above** the species' configured minimum. |
| **Flagged for review** | Measured length is **below** the configured minimum. An officer should inspect it. |
| **Pending review** | No length was measured, **or** the species has no minimum configured yet. |

Inspection outcomes: **Open** → **Warning issued** / **Referred for follow-up** → **Closed**.

## 5. Users and permissions

There are two kinds of accounts:

| | Normal user (e.g. data clerk) | Staff user (e.g. fisheries officer) |
|---|---|---|
| View everything, run reports, export CSV | ✅ | ✅ |
| Register catches, fishers, boats, inspections | ✅ | ✅ |
| Edit catches / inspections | Only their own | ✅ All |
| Add or edit **landing sites** and **species & size limits** | ❌ | ✅ |
| Delete catches | ❌ | ✅ |
| Open the **Admin** area (manage users) | ❌ | ✅ |

**To add a user:** sign in as a staff user → **Admin & users** (bottom of the left menu) → **Users → Add user**. Set a username and password, click *Save and continue editing*, then fill in their name. Tick **Staff status** only for people who should manage sites, species and other users. You don't need to tick any individual permissions; LakeWatch only looks at *Staff status*.

The account created with `createsuperuser` is a staff user automatically.

## 6. How the size check works

When a catch is saved, LakeWatch compares its **measured length** with its species' **minimum length**:

```
no length measured  OR  species has no minimum  →  Pending review
length  <  minimum                               →  Flagged for review
length  ≥  minimum                               →  Meets configured size
```

If a staff user later **changes a species' minimum**, every existing catch of that species is re-checked straight away, so the dashboard and reports always match the current rule.

Lengths must be greater than 0. Catch dates can't be in the future. Inactive sites and species can't be picked for new catches but stay on old records.

## 7. Settings (`.env` file)

LakeWatch works without any settings file. To change settings, copy `.env.example` to `.env` and edit it:

```powershell
copy .env.example .env      # Windows
```
```bash
cp .env.example .env        # macOS / Linux
```

| Setting | What it does | Default |
|---|---|---|
| `DJANGO_SECRET_KEY` | Secret used to sign logins. **Must** be changed on a server. | a development-only key |
| `DJANGO_DEBUG` | `True` shows detailed error pages. **Must be `False` on a server.** | `True` |
| `DJANGO_ALLOWED_HOSTS` | Comma-separated host names the site answers to. | `127.0.0.1,localhost` |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | Full HTTPS address(es) of the site, e.g. `https://lakewatch.example.org`. | empty |
| `DJANGO_TIME_ZONE` | Time zone used for "today" and timestamps. | `Africa/Kampala` |
| `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT` | PostgreSQL connection (see below). | not set → SQLite |
| `SQLITE_PATH` | Use a different SQLite file (handy for a separate practice database). | `db.sqlite3` in this folder |

Generate a strong secret key with:

```bash
python -c "from django.core.management.utils import get_random_secret_key as k; print(k())"
```

Never share or commit your `.env` file. It's already listed in `.gitignore`.

## 8. Using PostgreSQL

SQLite (the default) is fine for practice and a single computer. For several users or a server, use PostgreSQL 14+:

1. Create a database and user, for example `fish_landing_db`.
2. In `.env`, remove the `# ` in front of the `DB_...` lines and fill them in.
3. Run `python manage.py migrate` and `python manage.py createsuperuser`.

LakeWatch switches to PostgreSQL automatically whenever `DB_NAME` is set.

## 9. Running the tests

```bash
python manage.py test
```

The tests cover the size check, re-checking when a limit changes, form validation, permissions, filters, CSV export and the demo-data command.

## 10. Putting it on a server

This is a starting checklist. Get help from someone experienced with Django deployment if this is new to you.

1. Set `DJANGO_DEBUG=False`, a strong `DJANGO_SECRET_KEY`, correct `DJANGO_ALLOWED_HOSTS` and `DJANGO_CSRF_TRUSTED_ORIGINS` in `.env`. The app refuses to start with `DEBUG=False` and the default key.
2. Use PostgreSQL.
3. Run `python manage.py collectstatic` (files go to `staticfiles/`) and serve them with your web server (or add WhiteNoise).
4. Run the app with a production server such as Gunicorn (Linux) or Waitress (Windows) behind Nginx/IIS with **HTTPS**. With `DEBUG=False`, LakeWatch turns on secure cookies and HTTPS redirects.
5. Run `python manage.py check --deploy` and fix what it reports.
6. Set up **daily database backups**, logging and error monitoring.
7. Review privacy and data-retention rules for fishers' personal data (names, phone numbers).
8. Have fisheries staff test the workflow and verify **every** species limit before going live.

## 11. Troubleshooting

| Problem | Fix |
|---|---|
| `'python' is not recognized` | Use `py` instead of `python`, or reinstall Python with "Add to PATH" ticked. |
| `No module named 'django'` | The virtual environment isn't on. Run `venv\Scripts\Activate.ps1` (Windows) or `source venv/bin/activate`. |
| `no such table` / `no such column` | Run `python manage.py migrate`. |
| Forgot your password | `python manage.py changepassword <username>` |
| "You don't have permission to do that" | That action needs a staff user. Ask an administrator to tick *Staff status* on your account. |
| Can't choose a site or species when registering a catch | None exist yet, or they're marked inactive. A staff user must add or reactivate them. |
| `connection refused` with PostgreSQL | Check PostgreSQL is running and the `DB_...` values in `.env` are right, or comment them out to go back to SQLite. |
| Port 8000 already in use | `python manage.py runserver 8001`, then open http://127.0.0.1:8001/ |

## 12. Project structure

```text
config/                         Django settings (settings.py) and top-level URLs
monitoring/
  models.py                     Data: landing sites, species, fishers, boats, catches, inspections
  forms.py                      Input forms and their validation rules
  views.py                      Page logic (lists, forms, reports, CSV export, permissions)
  urls.py                       Page addresses
  admin.py                      Admin area set-up
  tests.py                      Automated tests
  management/commands/
    seed_demo.py                `python manage.py seed_demo`
  migrations/                   Database schema history
templates/monitoring/           Website pages (HTML)
templates/registration/         Sign-in page
static/css/app.css              Styling
static/js/app.js                Dashboard chart and mobile menu
.env.example                    Example settings file
requirements.txt                Python packages
```

### Possible next steps
- Change history (audit trail) for edits to catches and inspections
- Restricting users to their own landing sites
- An API (Django REST Framework) for mobile data collection
- Photo-based length measurement, once the manual workflow is proven
