# Technician Guide

**Permission type:** `ALL_TOPIC`  
**Template:** `super_admin.html`  
**Assigned to:** Technical staff responsible for monitoring the health of all stations on the system.

---

## What You See After Logging In

You are taken to the **All-Stations Map view**. This shows every station registered in the system, regardless of which broker or group it belongs to.

```
┌──────────────────────────────────────────────────────────┐
│ [Sidebar - 300px wide]  │  [Map - fills remaining space] │
│                         │                                 │
│  Logo                   │        Google Map               │
│  "Logged in as X"       │                                 │
│  [Logout]               │  ●  ●  ●  ●  ●  ●  ●  ●        │
│                         │  (all stations, coloured by     │
│  Loading progress       │   how recently data arrived)    │
│  Valid tables: N        │                                 │
│  Invalid tables: N      │                                 │
│                         │                                 │
│  [Problem Stations]     │                                 │
│                         │                                 │
│  ───── (after load) ─── │                                 │
│  Tabs: Map Legend  |    │                                 │
│        Manage Stations  │                                 │
└──────────────────────────────────────────────────────────┘
```

---

## Loading the Map

When the page loads, all station data is fetched in sequence. The sidebar shows:

```
Progress: 34/180 (19%)
Valid tables: 31
Invalid tables: 3
Time elapsed: 12 seconds
```

- **Valid tables:** Stations that returned usable data.
- **Invalid tables:** Stations registered in the system but with missing data, no coordinates, or other issues.

Loading can take 30–90 seconds depending on the number of stations. Once complete, the tabs appear in the sidebar.

---

## Marker Colours

| Colour | Last data received |
|--------|-------------------|
| 🟢 Green | Within the last 6 hours — station is active |
| 🟠 Orange | 6–12 hours ago |
| 🔴 Red | 12–24 hours ago |
| ⚫ Black | More than 24 hours ago — station is silent |

---

## Sidebar Tabs (After Load)

Once all stations have loaded, two tabs appear:

### Map Legend tab

Shows the colour legend with live counts:
```
● Within the last 6 hours      (45)
● Between 6 and 12 hours ago   (12)
● Between 12 and 24 hours ago  (8)
● More than 24 hours ago       (27)
```

### Manage Stations tab

An accordion list of all stations, organised by group. Expand a group to see its stations listed. Click a station name to open its Grafana dashboard.

---

## Problem Stations Modal

The **Problem Stations** button (visible before and after loading) opens a full-screen modal with two lists:

### Stations with Invalid Data

A list of stations that returned data but with issues (e.g. measurements out of range, unparseable values). These stations may appear on the map but their data cannot be relied upon.

There is a **Download CSV Data** button to export this list.

### Stations without Coordinates

A list of stations that have no `latitude`/`longitude` set in the database. These stations exist in the system but cannot be plotted on the map — they are invisible unless you check this list.

There is a **Download CSV Data** button to export this list too.

**What to do with this information:**
- For stations with invalid data: investigate the MQTT payload format or contact the station operator.
- For stations without coordinates: an admin needs to set the `longitude` and `latitude` values in the Dashboard Admin panel.

---

## Viewing a Station's Data

**Click any map marker** to open that station's Grafana dashboard. The dashboard shows all measurements for that station including time-series charts and (if configured) wind rose diagrams.

You can also use the **Manage Stations accordion** in the sidebar to navigate to a specific station without having to find it on the map.

---

## What You Cannot Do

The technician view is **read-only for station data**. You can view all stations and their dashboards, but you cannot:

- Add or remove stations.
- Edit measurement configurations.
- Manage user accounts or permissions.
- Change broker settings.

For any of those actions, contact a system administrator (or ask to be upgraded to an ADMIN account).

---

## Mobile Use

On phones and tablets, the sidebar slides up from the bottom. The map fills the screen and a dark drawer handle is visible at the top. Tap it to reveal the sidebar with the progress information and tabs.

---

## Keyboard Shortcuts

None are defined. All interactions are mouse/touch-based.

---

## Troubleshooting

| Problem | Likely cause | What to do |
|---------|-------------|-----------|
| Page takes very long to load | Many stations (100+) | Normal. Wait up to 2 minutes. |
| Many black stations all at once | Broker down or network outage | Check `journalctl -u mqtt_subscriber -f` on the server |
| A station appears in "Invalid" list | Malformed data from the station | Forward the station ID to the subscriber operator for investigation |
| Station exists in DB but not on map | Missing coordinates | Open Problem Stations → "without Coordinates" list; report to admin |
| Map does not load | Google Maps API error | Refresh the page. If persistent, check the API key (contact admin) |

---

## Navigation

← [end-user/README.md](README.md) | [docs/README.md](../README.md)
