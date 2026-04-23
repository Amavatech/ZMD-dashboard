# End-User Guide — Overview

This folder contains usage instructions for people who log in to the dashboard. It is written for non-technical users who need to view station data, manage stations, or administer the system.

---

## Contents

- [logging-in.md](logging-in.md) — How to log in and what to do if you cannot
- [standard-user.md](standard-user.md) — Single-station viewers (TOPIC permission)
- [group-user.md](group-user.md) — Group station viewers (GROUP permission)
- [technician.md](technician.md) — Technicians viewing all stations (ALL_TOPIC permission)
- [admin.md](admin.md) — System administrators (ADMIN permission)

---

## User Types at a Glance

When you log in, the dashboard automatically directs you to the correct view based on your account's permission level. There are four types of user:

| User Type | Permission | What They See |
|-----------|-----------|---------------|
| **Standard User** | `TOPIC` | Map with their one assigned station; click to open its Grafana charts |
| **Group User** | `GROUP` | Map showing all stations in their assigned group |
| **Technician** | `ALL_TOPIC` | Map showing every station on the system, with health monitoring tools |
| **Administrator** | `ADMIN` | Full admin panel — manage users, brokers, groups, and dashboards |

> **Special case — GEOSS Viewer:** Users in group 3 are redirected to a special static map showing GEOSS network stations in Stellenbosch, South Africa. Their interface is documented in [group-user.md](group-user.md).

---

## Map Legend (All Map Views)

All map views use the same colour coding for station markers:

| Colour | Meaning |
|--------|---------|
| 🟢 **Green** | Data received within the last 6 hours — station is active |
| 🟠 **Orange** | Data received 6–12 hours ago — likely still OK |
| 🔴 **Red** | Data received 12–24 hours ago — worth investigating |
| ⚫ **Black** | No data received in over 24 hours — station is silent |

---

## Getting an Account

Contact your system administrator. They can create an account for you via the admin panel at `/admin`. You will be given a username (email address) and a password. See [logging-in.md](logging-in.md) for how to use them.

---

## Navigation

← [docs/README.md](../README.md)
