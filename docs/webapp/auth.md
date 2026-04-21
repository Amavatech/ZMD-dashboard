# Authentication & Permissions

**File:** `mqtt_dashboard/auth/auth.py`  
**Blueprint prefix:** `/` (no prefix — login lives at `/login`)

---

## Overview

The application uses **Flask-Login** for session management. Users authenticate with email + password (bcrypt hashed with `werkzeug.security`). After login, Flask-Login stores the `userID` in a signed session cookie.

---

## Auth Routes

| Route | Method | Description |
|-------|--------|-------------|
| `/login` | GET | Renders `login.html` |
| `/login` | POST | Validates credentials, starts session, redirects to `/` |
| `/signup` | GET | Renders `signup.html` |
| `/signup` | POST | Creates new user with hashed password, redirects to `/login` |
| `/logout` | GET | Clears session, redirects to `/login` |

### Login Flow (step by step)

1. Browser `POST /login` with `email`, `password`, `remember`.
2. `User.query.filter_by(email=email).first()` — lookup by email.
3. `check_password_hash(user.password, password)` — verify bcrypt hash.
4. If valid: `login_user(user, remember=remember)` starts the session.
5. Redirect to `main.main` (`/`), which inspects the user's permissions to decide which template to render.
6. If invalid: flash error message, render `login.html` again.

---

## User Roles & Permission Types

Permissions are stored in the `permissions` table (see [models.md](models.md)). Each row links a user to a scope (topic, group, or global) and carries a `type` string.

### Permission Type Reference

| Type | Meaning | Where Used |
|------|---------|-----------|
| `ADMIN` | Full system administrator — can manage all brokers, users, groups, topics | Redirected to `/admin` on login |
| `GROUP_ADMIN` / `GADMIN` / `GDMIN` / `GROUP_ADMI` | (Variant spellings) Group-level administrator — same check as `ADMIN` for access gates | Treated as admin |
| `ALL_TOPIC` | "Technician" — read access to every topic | Redirected to `super_admin.html` |
| `GROUP` | Access to all topics within a specific group | Redirected to `group_user.html` |
| `TOPIC` | Access to one specific topic (by `tableID`) | Redirected to `standard_user.html` |

> **Variant spellings of admin:** The codebase checks for `ADMIN`, `GROUP_ADMIN`, `GROUP_ADMI`, `GADMIN`, and `GDMIN` to be safe across migrations. Prefer `ADMIN` when creating new admin users.

### How the Login Redirect Works (`/` route)

The `/` route (`main.main` function) checks the user's permissions in this order:

```
admin AND no groupID  → redirect to /admin
groupID == 3          → redirect to /geoss_stations
admin AND has groupID → redirect to /sub_admin
standard TOPIC user AND no groupID → render standard_user.html
GROUP permissions → render group_user.html
ALL_TOPIC          → render super_admin.html
fallback           → render layout.html
```

---

## Creating the First Admin User

Use the helper script (run once after initial setup):

```bash
cd /home/ubuntu/mqtt_dashboard
./venv/bin/python mqtt_dashboard/create_mqtt_user.py
```

Alternatively, insert a user directly in psql:

```sql
-- hashed password for "mypassword" using werkzeug sha256 method
INSERT INTO users (email, name, password)
VALUES ('admin@example.com', 'Admin', 'sha256$...');

-- Grant full admin permission
INSERT INTO permissions (userid, type, tableid, groupid)
VALUES (<new_userid>, 'ADMIN', NULL, NULL);
```

---

## Password Storage

Passwords are hashed using werkzeug's `generate_password_hash(password, method='sha256')` before storage. Plain-text passwords are **never** stored. 

> In newer versions of werkzeug the `method='sha256'` parameter is deprecated in favour of `scrypt`. If upgrading werkzeug, existing password hashes remain valid because `check_password_hash` detects the algorithm from the hash prefix.

---

## Session Security

- Session cookies are signed with the `Flask.Secret Key` from `config.ini`.
- Changing the secret key invalidates all active sessions.
- `remember=True` sets a persistent cookie (browser-session vs. long-term).
- All `@login_required` routes redirect to `/login` automatically if not authenticated.

---

## Navigation

← [webapp/README.md](README.md) | [docs/README.md](../README.md)
