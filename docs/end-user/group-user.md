# Group User Guide

**Permission type:** `GROUP`  
**Templates:** `group_user.html` (standard groups) or `geoss_stations.html` (Group 3 — GEOSS)  
**Assigned to:** Users who need to monitor a defined collection of stations.

---

## What You See After Logging In

You are taken to the **Group Map view**. Your sidebar and map look and work the same way as the standard user view, but your map shows **all stations in your assigned group** rather than just one.

```
┌──────────────────────────────────────────────────────────┐
│ [Sidebar - 300px wide]  │  [Map - fills remaining space] │
│                         │                                 │
│  Logo                   │       Google Map                │
│  "Logged in as X"       │                                 │
│  [Logout]               │   ●  ●  ●  ●  ●  ●             │
│                         │  (multiple station markers)     │
│  Loading spinner        │                                 │
│  Progress: 0/N (0%)     │                                 │
│  Time elapsed: 0s       │                                 │
│  Colour legend          │                                 │
│                         │                                 │
└──────────────────────────────────────────────────────────┘
```

### Loading Progress

Because your view loads data for multiple stations, the sidebar shows a loading counter:

```
Progress: 12/47 (26%)
Time elapsed: 8 seconds
```

Each station is fetched in turn. Once all stations have loaded, the spinner disappears and all markers are visible on the map.

---

## Marker Colours

Same as all other map views:

| Colour | Last data received |
|--------|-------------------|
| 🟢 Green | Within the last 6 hours |
| 🟠 Orange | 6–12 hours ago |
| 🔴 Red | 12–24 hours ago |
| ⚫ Black | More than 24 hours ago |

Additionally, the sidebar shows a count next to each colour:
```
● Within the last 6 hours  (12)
● Between 6 and 12 hours  (3)
● Between 12 and 24 hours  (1)
● More than 24 hours ago   (2)
```

This lets you immediately see at a glance how many stations in your group are active.

---

## Viewing a Station's Data

**Click any station marker** to open that station's Grafana dashboard in a full-screen modal overlay. The dashboard shows all measurements configured for that station: time-series graphs, wind roses, and latest-value tables.

Close the modal to return to the map.

---

## Sidebar on Mobile

On phones and tablets, the sidebar is hidden by default. The map fills most of the screen and a dark drawer handle appears at the top. Tap it to view the colour legend and your login status.

---

## Special Case: GEOSS Viewer (Group 3)

If your account is assigned to **Group 3 (GEOSS)**, you are redirected to a different, simplified map called `geoss_stations.html`. This shows a hardcoded set of GEOSS network stations near Stellenbosch, South Africa.

**Differences from the standard group view:**
- Station positions are **fixed** (hard-coded in the template, not from the database).
- Clicking a station opens its Grafana topic page directly at `/topic/<id>`.
- There is no sidebar progress bar — the stations load instantly.
- The map is centred on Stellenbosch (`-34.17°S, 18.93°E`) and does not pan to a different region.

This view is read-only and works the same way as the standard group view in all other respects.

---

## What You Cannot Do

Group users have **read-only** access. You cannot:
- See stations outside your assigned group.
- Change station settings or measurement configurations.
- Add, edit, or remove stations.
- Access the admin panel.

Contact your administrator if you need access to a different group or to additional stations.

---

## Troubleshooting

| Problem | Likely cause | What to do |
|---------|-------------|-----------|
| Progress bar stops partway | One or more stations has no data | Normal — stations with errors are still counted |
| Many black markers | Network outage or station power issue | Contact the station operators or your admin |
| Some stations missing from map | Station not assigned to your group, or coordinates not set | Contact admin |
| Takes a long time to load | Large group (50+ stations) | Normal — allow 30–60 seconds for large groups |

---

## Navigation

← [end-user/README.md](README.md) | [docs/README.md](../README.md)
