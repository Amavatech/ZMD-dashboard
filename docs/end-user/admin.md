# Administrator Guide

**Permission type:** `ADMIN` (also `GROUP_ADMIN`, `GADMIN`, `GDMIN`, `GROUP_ADMI`)  
**Template:** `admin.html` (main panel) + dedicated pages for each management area  
**Assigned to:** System administrators responsible for user management, broker configuration, and station organisation.

---

## What You See After Logging In

Administrators are taken to the **Admin Panel** — a user management page showing a list of all registered users.

```
┌─────────────────────────────────────────────────────────┐
│  [Create User]                                          │
│  [Manage Groups]  [Manage Brokers]  [Manage Dashboards] │
│  [Logout]                                               │
├─────────────────────────────────────────────────────────┤
│  Search users by email or name:  [____________]         │
├─────────────────────────────────────────────────────────┤
│  #   Name            Email             Actions          │
│  1   Alice Jones     alice@example.com  [Edit][Delete]  │
│  2   Bob Smith       bob@example.com    [Edit][Delete]  │
│  ...                                                    │
└─────────────────────────────────────────────────────────┘
```

---

## Managing Users

### Creating a New User

1. Click **Create User**.
2. Fill in the **Name**, **Email**, and **Password**.
3. Click **Submit**.

The user is created with no permissions. They will see a blank screen when they log in until you assign them a permission.

### Searching for a User

Type in the search box to filter the user list by name or email address. The table updates in real time as you type.

### Editing a User

Click **Edit** next to a user's row to open a form where you can:
- Change their name.
- Change their email address.
- Set or reset their password.
- Assign or change their **permission type** and the associated topic or group.

### Deleting a User

Click **Delete** next to a user's row. You will be asked to confirm. This is irreversible.

---

## Permission Types

When editing a user, you assign them a permission type:

| Type | Effect | When to use |
|------|--------|------------|
| `TOPIC` | Access to one station. Requires selecting a specific topic from the list. | A forecaster or station operator who only needs one station |
| `GROUP` | Access to all stations in one group. Requires selecting a group. | A regional manager overseeing a set of stations |
| `ALL_TOPIC` | View-only access to every station. No topic or group required. | A technician monitoring all stations |
| `ADMIN` | Full administrative access. No topic or group required. | A system administrator (only assign to trusted staff) |

> Variant spellings for ADMIN (`GROUP_ADMIN`, `GADMIN`, `GDMIN`, `GROUP_ADMI`) all grant the same admin access and are treated identically in the login redirect logic.

---

## Managing Groups — `/group_admin`

Click **Manage Groups** from the admin panel (or navigate to `/group_admin`).

```
┌──────────────────────────────────────────────────────────────┐
│  Groups            │ Added Tables (for selected group)        │
│                    │                                          │
│  [Group list]      │  [List of topics in this group]          │
│  [Remove Group]    │  [Remove Table from Group]               │
│                    │                                          │
│  [Group name input]│ All Tables (available to assign)         │
│  [Add New Group]   │  [List of all topics not in any group]   │
│                    │  [Add Table to Group]                    │
└──────────────────────────────────────────────────────────────┘
```

### Create a Group

1. Type the group name in the text field at the bottom-left.
2. Click **Add New Group**.

### Assign a Station to a Group

1. Select the group from the **Groups** list.
2. In the **All Tables** panel on the right, find the station topic.
3. Select it and click **Add Table to Group**.

The station will now appear in the **Added Tables** panel and be visible to all users assigned to that group.

### Remove a Station from a Group

1. Select the group.
2. Select the topic in the **Added Tables** panel.
3. Click **Remove Table from Group**.

### Delete a Group

1. Select the group.
2. Click **Remove Group**.

> **Note:** Deleting a group does not delete the stations in it — it only removes the group record. Users assigned to that group will no longer see it after their next login.

---

## Managing Brokers — `/broker_admin`

Click **Manage Brokers** from the admin panel (or navigate to `/broker_admin`).

```
┌──────────────────────────────────────────────────────────┐
│  Brokers          │  Details (for selected broker)        │
│                   │                                        │
│  ID | Name | URL  │  Name: [__________]                   │
│  -----------      │  URL:  [__________]                   │
│  1  | Main  | ... │  Port: [__________]                   │
│  2  | Backup| ... │  Auth: [checkbox]                     │
│                   │  User: [__________]                   │
│  [Remove Broker]  │  Pass: [__________]                   │
│                   │  [Edit Broker]  [Add Broker]          │
└──────────────────────────────────────────────────────────┘
```

### Add a Broker

1. Fill in all the fields in the Details panel (Name, URL, Port, credentials).
2. Click **Add Broker**.

The MQTT subscriber service is notified automatically via shared memory — **no restart required**.

### Edit a Broker

1. Click the broker row in the table to load its details.
2. Edit the fields.
3. Click **Edit Broker**.

> **Important:** After editing, the subscriber disconnects from the old broker address and reconnects to the new one automatically. There may be a gap of a few seconds in data collection.

### Remove a Broker

1. Select the broker in the table.
2. Click **Remove Broker**.

All stations associated with this broker will stop receiving data. Their hypertables and metadata rows remain in the database but no new data will arrive.

---

## Managing Dashboards — `/dashboard_admin`

Click **Manage Dashboards** from the admin panel (or navigate to `/dashboard_admin`).

```
┌─────────────────────────────────────────────────────────────────┐
│  Dashboards (topics)  │  Measurements (for selected topic)       │
│                       │                                          │
│  ID | Topic           │  ID | Name | Nickname | Visible | Graph  │
│  ─────────────────    │  ──────────────────────────────────────  │
│  42 | data-incoming/..│  1  | Temp | Air Temp |   Yes   | LINE   │
│  43 | data-incoming/..│  2  | WSpd | Wind     |   Yes   | ROSE   │
│                       │                                          │
│  [Delete Topic]       │  [Edit] fields, [Save Measurement]       │
│                       │  [Rebuild Grafana Dashboard]             │
└─────────────────────────────────────────────────────────────────┘
```

### View Measurements for a Topic

1. Click any topic row in the **Dashboards** list.
2. The **Measurements** panel fills with all sensor fields for that topic.

### Edit a Measurement

Select a measurement row to load it into the edit form. You can change:

| Field | Purpose |
|-------|---------|
| **Nickname** | Display name shown in Grafana instead of the raw field name (e.g. rename `AirTemp_Avg` to `Air Temperature`) |
| **Visible** | Whether this measurement appears in the Grafana dashboard. Set to `No` to hide sensor noise without deleting the data. |
| **Graph type** | `LINE` (time-series chart), `ROSE` (wind rose), or blank (latest-value table) |
| **Unit** | The unit suffix displayed in Grafana (e.g. `°C`, `m/s`, `hPa`) |
| **Status** | Whether to display the latest value as a status readout rather than a chart |

Click **Save** (or the equivalent button) to save. Then click **Rebuild Grafana Dashboard** to regenerate the Grafana panels with the new settings.

### Rebuild a Grafana Dashboard

If a station's Grafana dashboard is missing, broken, or out of date:

1. Select the topic in the **Dashboards** list.
2. Click **Rebuild Grafana Dashboard**.

The dashboard is regenerated from scratch using the current measurement configuration. The Grafana UID stored in the database is updated.

### Delete a Topic

1. Select the topic in the **Dashboards** list.
2. Click **Delete Topic**.

> **Warning:** This removes the `timestream_tables` metadata row and all associated measurements and permissions from the relational database. The **physical hypertable** (actual time-series data) is **not** dropped automatically — contact a server administrator to remove it if needed.

---

## Navigating the Admin Interfaces

All admin pages share a navigation bar at the top:

```
[Logo]  User Admin  |  Dashboard Admin  |  Broker Admin  |  Group Admin  |  Exit
```

Click **Exit** to return to your default landing page.

---

## Creating the First Admin Account

If the system has just been set up and no admin account exists yet, see the technical instructions in [docs/webapp/auth.md](../webapp/auth.md#creating-the-first-admin-user).

---

## Navigation

← [end-user/README.md](README.md) | [docs/README.md](../README.md)
