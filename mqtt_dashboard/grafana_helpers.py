import configparser
import logging
from math import fabs
import os,requests,json
import copy
from sqlalchemy import null
from mqtt_dashboard import models
from mqtt_dashboard import db
import pprint

script_dir = os.path.dirname(os.path.realpath(__file__))

config = configparser.ConfigParser()
config.read(script_dir+'/config.ini')

grafana_url=f"{config['Grafana']['Address']}:{config['Grafana']['Port']}"
grafana_subpath = config['Grafana'].get('Subpath', '')
if grafana_subpath:
    grafana_url = grafana_url + grafana_subpath

header={"Authorization":f"Bearer {config['Grafana']['API_Key']}","Content-Type":"application/json","Accept":"application/json"}
d_type = "postgres"


def _get_datasource_uid() -> str:
    """Fetch the PostgreSQL datasource UID from Grafana at call time (not import time)."""
    try:
        r = requests.get(url=f"{grafana_url}/api/datasources", headers=header, timeout=5)
        for dsource in r.json():
            if dsource["type"] in ["postgres", "grafana-postgresql-datasource"]:
                return dsource['uid']
    except Exception:
        pass
    return ""

def _normalize_table_name(topic):
    """Normalize topic to TimescaleDB hypertable name (matches ingest worker)."""
    # Replace slashes and hyphens with underscores, lowercase, and truncate to 63 chars
    name = topic.lower().replace('/', '_').replace('-', '_')
    return name[:63]

panel_template_time_series = {
  "gridPos": {
  "h": 9,
  "w": 12,
  "x": 1,
  "y": 0
  },
  "datasource": {
    "type": "postgres",
    "uid": ""
  },
  "fieldConfig": {
    "defaults": {
      "color": {
        "mode" : "fixed",
        "fixedColor": "yellow"
      },
      "custom": {
        "axisCenteredZero": False,
        "axisColorMode": "text",
        "axisLabel": "",
        "axisPlacement": "auto",
        "barAlignment": 0,
        "drawStyle": "line",
        "fillOpacity": 22,
        "gradientMode": "none",
        "hideFrom": {
          "legend": False,
          "tooltip": False,
          "viz": False
        },
        "lineInterpolation": "linear",
        "lineWidth": 1,
        "pointSize": 5,
        "scaleDistribution": {
          "type": "linear"
        },
        "showPoints": "auto",
        "spanNulls": False,
        "showPoints": "always",
        "stacking": {
          "group": "A",
          "mode": "none"
        },
        "thresholdsStyle": {
          "mode": "off"
        }
      },
      "mappings": [],
      "thresholds": {
        "mode": "absolute",
        "steps": [
          {
            "color": "green"
          },
          {
            "color": "yellow",
            "value": 80
          }
        ]
      }
    },
    "overrides": []
  },
  "id": None,
  "options": {
    "legend": {
      "calcs": [],
      "displayMode": "list",
      "placement": "bottom",
      "showLegend": True
    },
    "tooltip": {
      "mode": "single",
      "sort": "none"
    }
  },
  "pluginVersion": "9.1.6",
  "targets": [
    {
      "datasource": {
      "type": "postgres",
      "uid": ""
      },
      "rawQuery": True,
      "format": "time_series",
      "rawSql": "SELECT time, measure_value_double as value FROM public.placeholder_table WHERE measure_name='Visibility_m' ORDER BY time"
    }
  ],
  "title": "Panel Title",
  "type": "timeseries"
}

panel_template_table = {
    "gridPos": {
    "h": 9,
    "w": 12,
    "x": 1,
    "y": 0
  },
      "datasource": {
        "type": "postgres",
        "uid": ""
      },
      "fieldConfig": {
        "defaults": {
          "color": {
            "mode": "thresholds"
          },
          "custom": {
            "align": "auto",
            "displayMode": "auto",
            "inspect": False
          },
          "mappings": [],
          "thresholds": {
            "mode": "absolute",
            "steps": [
              {
                "color": "green",
                "value": None
              },
              {
                "color": "red",
                "value": 80
              }
            ]
          }
        },
        "overrides": []
      },
      "id": None,
      "options": {
        "footer": {
          "fields": "",
          "reducer": [
            "sum"
          ],
          "show": False
        },
        "showHeader": True
      },
      "pluginVersion": "9.1.6",
      "targets": [
        {
          "datasource": {
            "type": "postgres",
            "uid": ""
          },
          "rawQuery": True,
          "format": "table",
          "rawSql": "SELECT time, measure_value_varchar as value FROM public.placeholder_table WHERE measure_name='Vis_Units' ORDER BY time"
        }
      ],
      "title": "Panel Title",
      "type": "table"
    }

dashboard_template = {
    "dashboard": {
        "editable": True,
        "fiscalYearStartMonth": 0,
        "graphTooltip": 0,
        "id": None,
        "links": [],
        "liveNow": False,
        "panels": [
        ],
        "refresh": False,
        "schemaVersion": 37,
        "style": "dark",
        "tags": [],
        "templating": {
            "list": []
        },
        "timepicker": {},
        "timezone": "browser",
        "title": "",
        "uid": None,
        "version": 0,
        "weekStart": ""}
}

panel_template_rose = {
  "gridPos": {
    "h": 12,
    "w": 12,
    "x": 0,
    "y": 36
  },
  "type": "fatcloud-windrose-panel",
  "title": "",
  "transformations": [
    {
      "id": "prepareTimeSeries",
      "options": {
        "format": "many"
      }
    }
  ],
  "datasource": {
    "type": "postgres",
    "uid": ""
  },
  "pluginVersion": "9.2.4",
  "pconfig": {
    "layout": {
      "autosize": False,
      "font": {
        "color": "rgb(110,110,110)",
        "family": "\"Open Sans\", Helvetica, Arial, sans-serif"
      },
      "hovermode": "closest",
      "legend": {
        "orientation": "v"
      },
      "paper_bgcolor": "transparent",
      "plot_bgcolor": "transparent",
      "polar": {
        "angularaxis": {
          "direction": "counterclockwise",
          "dtick": 22.5,
          "rotation": 0
        },
        "radialaxis": {
          "ticksuffix": "%",
          "angle": 90
        }
      },
      "showlegend": True
    },
    "mapping": {
      "color": "@index",
      "x": "direction",
      "y": "speed",
      "size": None,
      "z": None
    },
    "settings": {
      "color_option": "ramp",
      "displayModeBar": False,
      "marker": {
        "color": "#33B5E5",
        "colorscale": "YIOrRd",
        "showscale": True,
        "size": 15,
        "sizemin": 3,
        "sizemode": "diameter",
        "sizeref": 0.2,
        "symbol": "circle"
      },
      "petals": 32,
      "plot": "windrose",
      "wind_speed_interval": 0.5
    }
  },
  "targets": [
    {
      "datasource": {
        "type": "postgres",
        "uid": ""
      },
      "rawQuery": True,
      "format": "table",
      "rawSql": "",
      "refId": "A"
    }
  ],
  "transparent": True
}

def create_dashboard_user(u:models.User):
    if(u.db_uid!=null):
        r=requests.delete(url=f"{grafana_url}/api/dashboards/uid/{u.db_uid}",headers=header,verify=False)
    added_measurements=[]
    panels=[]
    d_uid = _get_datasource_uid()
    permissions=u.permissions
    for p in permissions:
        if p.type=="TOPIC":
            measurements=db.session.query(models.timestream_measurement).filter(models.timestream_measurement.tableID==p.tableID)
            for m in measurements:
                if(m.measurementID not in added_measurements):
                    new_panel=copy.deepcopy(panel_template_time_series)
                    if m.type=="VARCHAR":
                        new_panel=copy.deepcopy(panel_template_table)
                    new_panel['datasource']['uid'] = d_uid
                    new_panel['targets'][0]['datasource']['uid'] = d_uid
                    
                    table_name = f"st_{m.table.station_id}" if m.table.station_id else _normalize_table_name(m.table.topic)
                    
                    if d_type == "postgres":
                        if m.type == "VARCHAR":
                            new_panel['targets'][0]['rawSql'] = f"SELECT time, measure_value_varchar as value FROM public.{table_name} WHERE measure_name='{m.name}' AND $__timeFilter(time) ORDER BY time DESC LIMIT 1"
                            new_panel['targets'][0]['format'] = "table"
                        else:
                            new_panel['targets'][0]['rawSql'] = f"SELECT time AS \"time\", measure_value_double::double precision AS value, '{m.name}' AS metric FROM public.{table_name} WHERE measure_name='{m.name}' AND $__timeFilter(time) ORDER BY time"
                            new_panel['targets'][0]['format'] = "time_series"
                        new_panel['targets'][0]['rawQuery'] = True
                    else:
                        new_panel['targets'][0]['table']=f"\"{m.table.topic.replace('/','_')}\""
                        new_panel['targets'][0]['database']=f"\"{config['Timestream']['DataBase']}\""
                        new_panel['targets'][0]['rawQuery']=f"SELECT time,measure_value::double from $__database.$__table WHERE measure_name='{m.name}'"
                        if m.type=="VARCHAR":
                            new_panel['targets'][0]['rawQuery']=f"SELECT max(time) as time,measure_value::varchar from $__database.$__table WHERE measure_name='{m.name} GROUP BY measure_value::varchar'"

                    new_panel['gridPos']['y']=9*(len(panels)/2)
                    new_panel['gridPos']['x']=12*(len(panels)%2)
                    if m.nickname=="":
                        new_panel['title']=m.name
                    else:
                        new_panel['title']=m.nickname
                    panels.append(new_panel)
                    added_measurements.append(m.measurementID)

    data=copy.deepcopy(dashboard_template)
    data["dashboard"]['panels']=panels
    data["dashboard"]["title"]=f"{u.name}_{u.userID}"

    r=requests.post(grafana_url+'/api/dashboards/db',data=json.dumps(data),headers=header)
    
    print(r.json())
    u.db_uid=r.json()['uid']
    db.session.commit()

def _delete_dashboard_by_title(title: str) -> str:
  try:
    resp = requests.get(
      url=f"{grafana_url}/api/search",
      headers=header,
      params={"query": title},
      timeout=5,
    )
    if resp.ok:
      for item in resp.json():
        if item.get("type") == "dash-db" and item.get("title") == title:
          uid = item.get("uid", "")
          if uid:
            requests.delete(
              url=f"{grafana_url}/api/dashboards/uid/{uid}",
              headers=header,
              verify=False,
            )
            return uid
  except Exception as exc:
    logging.warning("Failed deleting dashboard by title=%s: %s", title, exc)
  return ""

def create_dashboard_table(t:models.timestream_table):
  title = t.station_id if t.station_id else t.topic
  if t.db_uid:
    requests.delete(url=f"{grafana_url}/api/dashboards/uid/{t.db_uid}",headers=header,verify=False)
  else:
    _delete_dashboard_by_title(title)

  measurements = db.session.query(models.timestream_measurement).filter(
    models.timestream_measurement.tableID == t.tableID
  )
  panels = []
  cum_height = [0, 0]
  time_series_count = 0
  table_count = 0
  d_uid = _get_datasource_uid()

  for m in measurements:
    if not m.visible:
      continue

    new_panel = copy.deepcopy(panel_template_time_series)
    h = 9

    if m.graph == "ROSE":
      new_panel = copy.deepcopy(panel_template_rose)
      h = 12

    if m.type == "VARCHAR" or m.status:
      new_panel = copy.deepcopy(panel_template_table)
      new_panel['gridPos']['h'] = 3
      h = 3
      table_count += 1
    else:
      time_series_count += 1

    new_panel['datasource']['uid'] = d_uid
    for _tgt in new_panel.get('targets', []):
      if isinstance(_tgt.get('datasource'), dict):
        _tgt['datasource']['uid'] = d_uid

    table_name = f"st_{t.station_id}" if t.station_id else _normalize_table_name(t.topic)

    if d_type == "postgres":
      if m.graph == "LINE" or (m.graph is None and m.type == "DOUBLE" and not m.status):
        new_panel['targets'][0]['rawSql'] = (
          f"SELECT time AS \"time\", measure_value_double::double precision AS value, '{m.name}' AS metric "
          f"FROM public.{table_name} "
          f"WHERE measure_name='{m.name}' AND $__timeFilter(time) "
          f"ORDER BY time"
        )
        new_panel['targets'][0]['format'] = "time_series"
      elif m.graph == "ROSE":
        new_panel['targets'][0]['rawSql'] = (
          f"WITH t AS (SELECT time, measure_value_double::double precision as direction from public.{table_name} "
          f"WHERE measure_name='{m.directionName}' ORDER BY time), "
          f"t2 AS (SELECT time, measure_value_double::double precision as speed from public.{table_name} "
          f"WHERE measure_name='{m.name}' ORDER BY time), "
          f"t3 AS (SELECT t.time, speed, direction from t INNER JOIN t2 ON t.time=t2.time) "
          f"SELECT time, speed, direction from t3"
        )
        new_panel['targets'][0]['format'] = "table"

      if m.type == "VARCHAR":
        new_panel['targets'][0]['rawSql'] = (
          f"SELECT time, measure_value_varchar as value FROM public.{table_name} "
          f"WHERE measure_name='{m.name}' AND $__timeFilter(time) "
          f"ORDER BY time DESC LIMIT 1"
        )
        new_panel['targets'][0]['format'] = "table"
      if m.status and m.type == "DOUBLE":
        new_panel['targets'][0]['rawSql'] = (
          f"SELECT time, measure_value_double::double precision as value FROM public.{table_name} "
          f"WHERE measure_name='{m.name}' AND $__timeFilter(time) "
          f"ORDER BY time DESC LIMIT 1"
        )
        new_panel['targets'][0]['format'] = "table"

      if not new_panel['targets'][0].get('rawSql'):
        new_panel['targets'][0]['rawSql'] = (
          f"SELECT time AS \"time\", measure_value_double::double precision AS value, '{m.name}' AS metric "
          f"FROM public.{table_name} "
          f"WHERE measure_name='{m.name}' AND $__timeFilter(time) "
          f"ORDER BY time"
        )
        new_panel['targets'][0]['format'] = "time_series"

      new_panel['targets'][0]['rawQuery'] = True
    else:
      new_panel['targets'][0]['table'] = f"\"{m.table.topic.replace('/','_')}\""
      new_panel['targets'][0]['database'] = f"\"{config['Timestream']['DataBase']}\""
      if m.graph == "LINE":
        new_panel['targets'][0]['rawQuery'] = (
          f"SELECT time,measure_value::double from $__database.$__table "
          f"WHERE measure_name='{m.name}' ORDER BY time"
        )
      elif m.graph == "ROSE":
        new_panel['targets'][0]['rawQuery'] = (
          f"WITH t AS (SELECT time,measure_value::double as direction from $__database.$__table "
          f"WHERE measure_name='{m.directionName}' ORDER BY time),"
          f"t2 AS (SELECT time,measure_value::double as speed from $__database.$__table "
          f"WHERE measure_name='{m.name}' ORDER BY time),"
          f"t3 AS( SELECT t.time,speed,direction from (t INNER JOIN t2 ON t.time=t2.time)) "
          f"SELECT time,speed,direction from t3"
        )
      if m.type == "VARCHAR":
        new_panel['targets'][0]['rawQuery'] = (
          f"SELECT max(time) as time,(measure_value::varchar) as value from $__database.$__table "
          f"WHERE measure_name='{m.name}' GROUP BY measure_value::varchar"
        )
      if m.status and m.type == "DOUBLE":
        new_panel['targets'][0]['rawQuery'] = (
          f"SELECT max(time) as time,(measure_value::double) as value from $__database.$__table "
          f"WHERE measure_name='{m.name}' GROUP BY measure_value::double"
        )

    col = len(panels) % 2
    new_panel['gridPos']['y'] = cum_height[col]
    new_panel['gridPos']['x'] = 12 * col
    if m.nickname == "":
      new_panel['title'] = m.name
    else:
      new_panel['title'] = m.nickname

    panels.append(new_panel)
    cum_height[col] += h

  data = copy.deepcopy(dashboard_template)
  data["dashboard"]['panels'] = panels
  data["dashboard"]["title"] = title
  data["overwrite"] = True

  r = requests.post(grafana_url+'/api/dashboards/db',data=json.dumps(data),headers=header)
  resp_json = r.json()
  t.db_uid = resp_json.get('uid', '')
  logging.info(
    "Created/updated Grafana dashboard for tableID=%s topic=%s panels=%s uid=%s",
    t.tableID,
    t.topic,
    len(panels),
    t.db_uid,
  )
  logging.info(
    "Panel breakdown for tableID=%s: time_series=%s table=%s",
    t.tableID,
    time_series_count,
    table_count,
  )
  db.session.commit()

def delete_dashboard_table(t:models.timestream_table):
  requests.delete(url=f"{grafana_url}/api/dashboards/uid/{t.db_uid}",headers=header,verify=False)
  t.db_uid=None

def update_snapshot_user(u:models.User)->str:
  if not u.db_uid:
    create_dashboard_user(u)
  if u.ss_key!="":
    requests.delete(url=grafana_url+"/api/snapshots/"+u.ss_key,headers=header)
  dash_resp=requests.get(url=grafana_url+"/api/dashboards/uid/"+u.db_uid,headers=header)
  if not dash_resp.ok:
    create_dashboard_user(u)
    dash_resp=requests.get(url=grafana_url+"/api/dashboards/uid/"+u.db_uid,headers=header)
  dash=dash_resp.json()
  r=requests.post(url=grafana_url+'/api/snapshots',data=json.dumps(dash),headers=header)
  snap_json=r.json()
  key=snap_json.get("key", "")
  u.ss_key=key
  db.session.commit()
  return key

def update_snapshot_table(u:models.timestream_table)->str:
  if not u.db_uid:
    create_dashboard_table(u)
  if u.ss_key!="":
    requests.delete(url=grafana_url+"/api/snapshots/"+u.ss_key,headers=header)
  dash_resp=requests.get(url=grafana_url+"/api/dashboards/uid/"+u.db_uid,headers=header)
  if not dash_resp.ok:
    create_dashboard_table(u)
    dash_resp=requests.get(url=grafana_url+"/api/dashboards/uid/"+u.db_uid,headers=header)
  dash=dash_resp.json()
  r=requests.post(url=grafana_url+'/api/snapshots',data=json.dumps(dash),headers=header,timeout=500)
  snap_json=r.json()
  key=snap_json.get("key", "")
  u.ss_key=key
  db.session.commit()
  return key