import configparser
from math import fabs
import os,requests,json
import copy
from sqlalchemy import null
import mySqlUtil
import configUtil

script_dir = os.path.dirname(os.path.realpath(__file__))

config = configparser.ConfigParser()
config.read(script_dir+'/config.ini')

grafana_url=f"{config['Grafana']['Address']}:{config['Grafana']['Port']}"

header={"Authorization":f"Bearer {config['Grafana']['API_Key']}","Content-Type":"application/json","Accept":"application/json"}
try:
  r=requests.get(url=f"{grafana_url}/api/datasources",headers=header,timeout=5)
  a=r.json()
except Exception:
  a=[]

d_uid=""

for dsource in a:
  if dsource["type"] in ["postgres", "grafana-postgresql-datasource"]:
    d_uid=dsource['uid']

panel_template_time_series = {
    "gridPos": {
    "h": 9,
    "w": 12,
    "x": 1,
    "y": 0
  },
    "datasource": {
      "type": "postgres",
      "uid": d_uid
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
        "overrides": [
            {
                "__systemRef": "hideSeriesFrom",
                "matcher": {
                    "id": "byNames",
                    "options": {
                        "mode": "exclude",
                        "names": [
                            "measure_value::double"
                        ],
                        "prefix": "All except:",
                        "readOnly": True
                    }
                },
                "properties": [
                    {
                        "id": "custom.hideFrom",
                        "value": {
                            "legend": False,
                            "tooltip": False,
                            "viz": True
                        }
                    }
                ]
            }
        ]
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
            "uid": d_uid
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
        "uid": d_uid
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
            "uid": d_uid
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
    "uid": d_uid
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
        "uid": d_uid
      },
      "rawQuery": True,
      "format": "table",
      "rawSql": "",
      "refId": "A"
    }
  ],
  "transparent": True
}

def create_dashboard_table(t:mySqlUtil.timestream_table,session):
    if(t.db_uid!=null):
        requests.delete(url=f"{grafana_url}/api/dashboards/uid/{t.db_uid}",headers=header,verify=False)
    measurements=session.query(mySqlUtil.timestream_measurement).filter(mySqlUtil.timestream_measurement.tableID==t.tableID)
    panels=[]
    cum_height=[0,0]
    for m in measurements:
        h=0
        if(not m.visible):
            continue
        
        # Initialize new_panel with a default based on type/status
        if(m.graph=="LINE"):
            h=9
            new_panel=copy.deepcopy(panel_template_time_series)
        elif(m.graph=="ROSE"):
            h=12
            new_panel=copy.deepcopy(panel_template_rose)
        elif m.type=="VARCHAR" or m.status:
            new_panel=copy.deepcopy(panel_template_table)
            new_panel['gridPos']['h']=3
            h=3
        else:
            # Default to time series for DOUBLE types without specified graph
            h=9
            new_panel=copy.deepcopy(panel_template_time_series)
        
        table_name = m.table.topic.replace('/','_')
        schema_name = "public"
        if(m.graph=="LINE"):
          new_panel['targets'][0]['rawSql']=f"SELECT time, measure_value_double as value FROM {schema_name}.\"{table_name}\" WHERE measure_name='{m.name}' ORDER BY time"
          new_panel['targets'][0]['format']="time_series"
          new_panel['targets'][0]['rawQuery']=True
        elif(m.graph=="ROSE"):
          new_panel['targets'][0]['rawSql']=f"WITH t AS (SELECT time, measure_value_double as direction FROM {schema_name}.\"{table_name}\" WHERE measure_name='{m.directionName}' ORDER BY time),t2 AS (SELECT time, measure_value_double as speed FROM {schema_name}.\"{table_name}\" WHERE measure_name='{m.name}' ORDER BY time),t3 AS( SELECT t.time,speed,direction from (t INNER JOIN t2 ON t.time=t2.time)) SELECT time,speed,direction from t3"
          new_panel['targets'][0]['format']="table"
          new_panel['targets'][0]['rawQuery']=True
        elif m.type=="VARCHAR":
          new_panel['targets'][0]['rawSql']=f"SELECT max(time) as time, (measure_value_varchar) as value FROM {schema_name}.\"{table_name}\" WHERE measure_name='{m.name}' GROUP BY measure_value_varchar"
          new_panel['targets'][0]['format']="table"
          new_panel['targets'][0]['rawQuery']=True
        elif m.status and m.type=="DOUBLE":
          new_panel['targets'][0]['rawSql']=f"SELECT max(time) as time, (measure_value_double) as value FROM {schema_name}.\"{table_name}\" WHERE measure_name='{m.name}' GROUP BY measure_value_double"
          new_panel['targets'][0]['format']="table"
          new_panel['targets'][0]['rawQuery']=True
        else:
          # Default query for DOUBLE types without graph specified
          new_panel['targets'][0]['rawSql']=f"SELECT time, measure_value_double as value FROM {schema_name}.\"{table_name}\" WHERE measure_name='{m.name}' ORDER BY time"
          new_panel['targets'][0]['format']="time_series"
          new_panel['targets'][0]['rawQuery']=True
        
        new_panel['gridPos']['y']=cum_height[(len(panels)%2)]
        new_panel['gridPos']['x']=12*(len(panels)%2)
        if m.nickname=="":
            new_panel['title']=m.name
        else:
            new_panel['title']=m.nickname

        panels.append(new_panel)
        cum_height[(len(panels)%2)]+=h
    data=dashboard_template
    data["dashboard"]['panels']=panels
    data["dashboard"]["title"]=f"{t.topic.replace('_','/')}"

    r=requests.post(grafana_url+'/api/dashboards/db',data=json.dumps(data),headers=header)
    print(r.json())
    t.db_uid=r.json()['uid']
    session.commit()

def update_snapshot_table(u:mySqlUtil.timestream_table,session)->str:
    if u.db_uid==null or u.db_uid=="":
        create_dashboard_table(u)
    if u.ss_key!="":
        r=requests.delete(url=grafana_url+"/api/snapshots/"+u.ss_key,headers=header)
    dash=requests.get(url=grafana_url+"/api/dashboards/uid/"+u.db_uid,headers=header).json()
    r=requests.post(url=grafana_url+'/api/snapshots',data=json.dumps(dash),headers=header)
    key=r.json()["key"]
    u.ss_key=key
    session.commit()
    return key