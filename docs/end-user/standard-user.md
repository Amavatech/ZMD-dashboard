# Standard User Guide

**Permission type:** `TOPIC`  
**Template:** `standard_user.html`  
**Assigned to:** Users who need to monitor a single weather station.

---

## What You See After Logging In

After login you are taken directly to the **Station Map view**. The screen is divided into two areas:

```
┌──────────────────────────────────────────────────────────┐
│ [Sidebar - 300px wide]  │  [Map - fills remaining space] │
│                         │                                 │
│  Logo                   │         Google Map              │
│  "Logged in as X"       │                                 │
│  [Logout]               │    (station marker appears      │
│                         │     at station's coordinates)   │
│  Loading spinner        │                                 │
│  Colour legend          │                                 │
│                         │                                 │
└──────────────────────────────────────────────────────────┘
```

When the page first loads, a **spinner** appears in the sidebar while the station data is being fetched. Once loading is complete the spinner disappears and your station's marker appears on the map.

---

## The Map

Your assigned station appears as a **coloured circle** on the map:

| Colour | Last data received |
|--------|-------------------|
| Green | Within the last 6 hours |
| Orange | 6–12 hours ago |
| Red | 12–24 hours ago |
| Black | More than 24 hours ago |

### Navigating the Map

- **Zoom in/out:** Scroll wheel, or the +/− buttons in the map corner.
- **Pan:** Click and drag.
- **Fullscreen:** Click the fullscreen icon (↔) in the top-left of the sidebar header.

---

## Viewing Station Data

**Click the station marker** on the map to open the station's Grafana dashboard in a modal overlay. This shows:

- **Time-series graphs** for each sensor measurement (temperature, humidity, wind speed, etc.)
- **Wind rose diagrams** for directional data (if configured)
- **Latest-value tables** for status measurements

The dashboard covers the default Grafana time range (typically the last 24 hours). Use the Grafana time-range picker in the dashboard to view historical data.

---

## The Sidebar (Mobile)

On small screens (phones/tablets) the sidebar slides up from the bottom:

1. A dark **drawer handle** bar appears at the top of the screen.
2. Tap it to slide the sidebar open.
3. The sidebar shows your login status and the colour legend.
4. The map fills the screen above the drawer handle.

---

## What You Cannot Do

Standard users have **read-only** access. You cannot:
- See or access other stations.
- Change any settings.
- Add or remove measurements.
- Access the admin panel.

If you need access to additional stations or need administrative changes made, contact your system administrator.

---

## Troubleshooting

| Problem | Likely cause | What to do |
|---------|-------------|-----------|
| Spinner never stops / map is empty | Station has no data or coordinates not set | Contact admin — the station's latitude/longitude may not be configured |
| Station marker is black | No data received in >24 hours | Contact admin — the station may be offline |
| Grafana dashboard shows "No data" | Measurement data gap | Check the time range in the Grafana panel; try selecting "Last 7 days" |
| Map does not load | Google Maps API issue | Refresh the page |

---

## Navigation

← [end-user/README.md](README.md) | [docs/README.md](../README.md)
