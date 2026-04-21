from operator import mod
from flask import Blueprint, render_template, url_for, request, redirect, flash, jsonify, send_file, current_app
from flask_login import login_required, current_user
from sqlalchemy import true, text
from flask_cors import CORS
from mqtt_dashboard.models import User
from mqtt_dashboard.models import timestream_measurement
from datetime import datetime, timedelta
from mqtt_dashboard import models
from mqtt_dashboard import db
from mqtt_dashboard import grafana_helpers
from werkzeug.security import generate_password_hash
import re
from multiprocessing import shared_memory
import json
import os
import requests

print(__name__)
main_bp=Blueprint("main",__name__, template_folder='../templates')
messages=shared_memory.ShareableList(name="messages")
def get_dbs():
    dbs=[]
    added_topics=[]
    perms=current_user.permissions
    for p in perms:
        if p.type=="GROUP":
            g=db.session.query(models.group).filter(models.group.groupID==p.groupID).first()
            if(not g):
                break
            tables=db.session.query(models.timestream_table).filter(models.timestream_table.groupID==p.groupID)
            for t in tables:
                if t.tableID not in added_topics:
                    added_topics.append(t.tableID)
            dbs.append({'url':f'/group/{g.groupID}','text':g.name})
    for p in perms:
        if p.type=="TOPIC":
            t=db.session.query(models.timestream_table).filter(models.timestream_table.tableID==p.tableID).first()
            if not t:
                continue
            url=t.tableID
            if t.tableID not in added_topics:
                dbs.append({'url':f'/topic/{url}','text':t.topic})
                added_topics.append(t.tableID)
        if p.type=="ALL_TOPIC":
            groups=db.session.query(models.group)

            for g in groups:
                tables=db.session.query(models.timestream_table).filter(models.timestream_table.groupID==g.groupID)
                for t in tables:
                    if t.tableID not in added_topics:
                        added_topics.append(t.tableID)
                dbs.append({'url':f'/group/{g.groupID}','text':g.name})
            tables=db.session.query(models.timestream_table)
            for t in tables:
                if t.tableID not in added_topics:
                    dbs.append({'url':f'/topic/{t.tableID}','text':t.topic})
                    added_topics.append(t.tableID)
    return dbs

ADMIN_PERMISSION_TYPES = {
    "ADMIN",
    "GROUP_ADMIN",
    "GROUP_ADMI",
    "GADMIN",
    "GDMIN",
}


def is_admin(user:User):
    for p in user.permissions:
        p_type = (p.type or "").upper()
        if p_type in ADMIN_PERMISSION_TYPES:
            return True
    return False

def is_group(user:User):
    for p in user.permissions:
        if (p.type=="GROUP"):
            return True
    return False

def is_technician(user:User):
    for p in user.permissions:
        if (p.type=="ALL_TOPIC"):
            return True
    return False

def is_standard_user(user:User):
    for p in user.permissions:
        if (p.type=="TOPIC"):
            return True
    return False



def get_longitude_latitude_for_user(user):
    longitude_latitude_data = []
    perms = user.permissions
    for p in perms:
        if p.type == "TOPIC":
            t = db.session.query(models.timestream_table).filter(models.timestream_table.tableID == p.tableID).first()
            if t:
                longitude_latitude_data.append({'longitude': t.longitude, 'latitude': t.latitude})

    return longitude_latitude_data



@main_bp.route("/")
@login_required
def main():
    dbs = get_dbs()
    try:
        # Get the group ID of the logged-in user
        group_id = None
        if current_user.is_authenticated:
            user_permissions = current_user.permissions
            for permission in user_permissions:
                if permission.groupID:
                    group_id = permission.groupID
                    break

        user_name = current_user.name if current_user.is_authenticated else None

        if current_user.is_authenticated:  # Verify the user is logged in
            if is_admin(current_user) and group_id is None:  # Check for admin status and group_id is None
                # Admin users get redirected to an admin-specific template
                 return redirect(url_for('main.admin'))
            elif group_id == 3:
                # Redirect to geoss_stations.html if the user is standard or group user and group_id is 3
                return redirect(url_for('main.geoss_stations'))
            elif is_admin(current_user) and group_id is not None:  # Check for admin status and group_id is not None
                # Admin users with a group_id get redirected to the sub_admin.html template
                 return redirect(url_for('main.sub_admin'))
            elif is_standard_user(current_user)and group_id is None:
                # Admin users with a group_id get redirected to the sub_admin.html template
                 return render_template('standard_user.html', user_name=user_name, dbs=dbs)
            elif is_group(current_user):  # Check for GROUP permissions
                # Users with GROUP permissions get a group-specific template
                return render_template('group_user.html', user_name=user_name, dbs=dbs)
            elif is_technician(current_user):  # Check for ALL_TOPIC permissions
                # Users with ALL_TOPIC permissions see a different template
                return render_template('super_admin.html', user_name=user_name, dbs=dbs)
            else:
                # Default user view if no specific permissions are found
                return render_template("layout.html", user_name=user_name, dbs=dbs)
            

    except Exception as e:
        return jsonify({'error': str(e)})



@main_bp.route("/user")
@login_required
def user():
    dbs=get_dbs()
    key=grafana_helpers.update_snapshot_user(current_user)
    return render_template('index.html',name=current_user.name,url=grafana_helpers.grafana_url+f'/dashboard/snapshot/{key}?kiosk=tv',dbs=dbs,is_admin=is_admin(current_user))

    

    

# Timescale + Relational Database Fetch   

@main_bp.route("/combined_data/<table_name>", methods=["GET"])
@login_required
def combined_data(table_name):
    
    try:
        # Resolve the actual topic-based table name for Timescale if provided with an ID
        timescale_name = table_name
        if str(table_name).isdigit():
            table = db.session.query(models.timestream_table).filter(models.timestream_table.tableID == int(table_name)).first()
            if table:
                timescale_name = f"st_{table.station_id}" if table.station_id else table.topic.replace("/", "_")

        # Fetch data from relational database
        try:
            relational_data = fetch_relational_data(table_name)
            relational_data_valid = True
        except Exception as relational_error:
            relational_data = {'error': str(relational_error)}
            relational_data_valid = False

        # Fetch data from TimescaleDB — no measure_names filter so all sensors are returned.
        # This ensures the timestamp reflects the true last-contact time regardless of field names.
        try:
            timescale_data = fetch_timescale_data(
                timescale_name,
                measure_names=None,
                latest_per_measure=True,
            )
            timescale_data_valid = True
        except Exception as timescale_error:
            current_app.logger.warning(
                "Timescale query failed for table=%s: %s",
                table_name,
                timescale_error,
            )
            timescale_data = []
            timescale_data_valid = False

        # Combine the data
        combined_data = {
            'relational_data': relational_data,
            'timescale_data': timescale_data,
        }

        # Print messages based on data validity
        if relational_data_valid and timescale_data_valid:
            print("Both relational and Timescale data fetched successfully.")
        elif relational_data_valid:
            print("Relational data fetched successfully. Timescale data is invalid.")
        elif timescale_data_valid:
            print("Timescale data fetched successfully. Relational data is invalid.")
        else:
            print("No data from both databases.")

        # Return the combined data as JSON
        return jsonify({'data': combined_data})

    except Exception as e:
        return jsonify({'error': str(e)})

# Function to fetch relational data remains unchanged
def fetch_relational_data(table_name):
    try:
        # Check if table_name is an ID
        if str(table_name).isdigit():
            table = db.session.query(models.timestream_table).filter(models.timestream_table.tableID == int(table_name)).first()
        else:
            # Convert underscores to slashes to match the topic column in the database
            formatted_table_name = table_name.replace("_", "/")
            # Find the table by formatted name
            table = db.session.query(models.timestream_table).filter(models.timestream_table.topic == formatted_table_name).first()

        if not table:
            return {'error': 'Table not found.'}

        # Get unique user IDs with permissions for the specified table
        permissions = db.session.query(models.permission).filter(models.permission.tableID == table.tableID, models.permission.type == "TOPIC").distinct(models.permission.userID).all()
        user_ids = [p.userID for p in permissions]

        # Get group name associated with the table
        group_id = table.groupID
        group = db.session.query(models.group).filter(models.group.groupID == group_id).first()
        group_name = group.name if group else None

        longitude = table.latitude
        latitude = table.longitude
        if longitude is not None:
            longitude = longitude
        if latitude is not None and latitude > 0:
            latitude = -latitude

        # Return data for the specified table along with user information
        table_info = {
            'name': table.station_id or table.topic.replace("/", "_"),
            'longitude': longitude,
            'latitude': latitude,
            'topic_id': table.tableID,
            'group_id': table.groupID,
            'group_name': group_name,
            'user_info': [],
        }

        for user_id in user_ids:
            user = db.session.query(models.User).filter(models.User.userID == user_id).first()
            if user:
                table_info['user_info'].append({
                    'user_id': user.userID,
                    'user_name': user.name,
                    'user_email': user.email,
                    # Add other user attributes as needed
                })

        # Return the table_info
        return table_info

    except Exception as e:
        return {'error': str(e)}

def resolve_timescale_table_ref(table_name: str):
    if not re.match(r"^[A-Za-z0-9_\-]+$", table_name or ""):
        raise ValueError("Invalid table name")

    def table_exists(name: str, schema: str = None) -> bool:
        if schema:
            ref = f'"{schema}"."{name}"'
        else:
            ref = f'"{name}"'
        return db.session.execute(text("SELECT to_regclass(:tbl)"), {"tbl": ref}).scalar() is not None

    full_name = table_name
    # candidates: original, normalized (lowercase, underscores, 63 chars), truncated original
    candidates = [full_name]
    
    # Matching ingestor normalization: name.lower().replace("-", "_")[:63]
    normalized = full_name.lower().replace("-", "_")[:63]
    if normalized not in candidates:
        candidates.append(normalized)

    truncated = full_name[:63]
    if truncated not in candidates:
        candidates.append(truncated)

    for candidate in candidates:
        for schema in ("public", "mqtt_dashboard", None):
            if table_exists(candidate, schema):
                if candidate != full_name:
                    current_app.logger.warning(
                        "Timescale table name truncated: requested=%s resolved=%s schema=%s",
                        full_name,
                        candidate,
                        schema or "search_path",
                    )
                return schema or "public", candidate

    if truncated != full_name:
        current_app.logger.warning(
            "Timescale table not found; tried full and truncated names: requested=%s truncated=%s",
            full_name,
            truncated,
        )
    return None, None


def derive_station_id_candidates(table_name: str):
    candidates = []
    if not table_name:
        return candidates

    # Extract station between last '-' and '_data_' if present
    match = re.search(r"-([^-/]+)_data_", table_name)
    if match:
        candidates.append(match.group(1))

    # Also try splitting on '_' and taking a likely station token
    parts = table_name.split("_")
    for token in parts:
        if token and token.lower() not in {"data", "incoming", "satellite", "synop", "cr1000x", "cr1000", "cr300", "cr350"}:
            candidates.append(token)

    # Deduplicate while preserving order
    seen = set()
    deduped = []
    for item in candidates:
        if item not in seen:
            seen.add(item)
            deduped.append(item)
    return deduped


def fetch_timescale_data(table_name, measure_names=None, limit=8, since_minutes=None, latest_per_measure=False):
    schema_name, resolved_table_name = resolve_timescale_table_ref(table_name)

    if resolved_table_name:
        if schema_name:
            from_clause = f'"{schema_name}"."{resolved_table_name}"'
        else:
            from_clause = f'"{resolved_table_name}"'

        params = {}
        filters = []

        if measure_names:
            filters.append("measure_name = ANY(:measure_names)")
            params["measure_names"] = measure_names

        if since_minutes is not None:
            filters.append("time >= now() - (:since_minutes * interval '1 minute')")
            params["since_minutes"] = since_minutes

        if latest_per_measure:
            sql_parts = [
                f'SELECT DISTINCT ON (measure_name) time, measure_name, COALESCE(measure_value_double::text, measure_value_varchar) AS value FROM {from_clause}'
            ]
            if filters:
                sql_parts.append("WHERE " + " AND ".join(filters))
            sql_parts.append("ORDER BY measure_name, time DESC")
        else:
            sql_parts = [
                f'SELECT time, measure_name, COALESCE(measure_value_double::text, measure_value_varchar) AS value FROM {from_clause}'
            ]
            if filters:
                sql_parts.append("WHERE " + " AND ".join(filters))
            sql_parts.append("ORDER BY time DESC")
            if limit is not None:
                sql_parts.append("LIMIT :limit")
                params["limit"] = limit

        query = " ".join(sql_parts)
        rows = db.session.execute(text(query), params).fetchall()

        results = []
        for row in rows:
            timestamp = row.time.isoformat() if row.time else None
            results.append([None, None, row.measure_name, timestamp, row.value])

        return results

    # Fallback to shared weather_data hypertable if per-topic table doesn't exist
    station_candidates = derive_station_id_candidates(table_name)
    for station_id in station_candidates:
        sql_parts = [
            "SELECT time, metric AS measure_name, value::text AS value FROM public.weather_data"
        ]
        params = {"station_id": station_id}
        filters = ["station_id = :station_id"]

        if measure_names:
            filters.append("metric = ANY(:measure_names)")
            params["measure_names"] = measure_names

        if since_minutes is not None:
            filters.append("time >= now() - (:since_minutes * interval '1 minute')")
            params["since_minutes"] = since_minutes

        if filters:
            sql_parts.append("WHERE " + " AND ".join(filters))

        sql_parts.append("ORDER BY time DESC")
        if limit is not None:
            sql_parts.append("LIMIT :limit")
            params["limit"] = limit

        query = " ".join(sql_parts)
        rows = db.session.execute(text(query), params).fetchall()
        if rows:
            current_app.logger.warning(
                "Timescale fallback used weather_data for station_id=%s",
                station_id,
            )
            results = []
            for row in rows:
                timestamp = row.time.isoformat() if row.time else None
                results.append([None, None, row.measure_name, timestamp, row.value])
            return results

    return []
    

@main_bp.route("/airport_data/<table_name>", methods=["GET"])
@login_required
def airport_data(table_name):
    
    try:
        # Fetch data from relational database
        try:
            relational_data = fetch_relational_data(table_name)
            relational_data_valid = True
        except Exception as relational_error:
            relational_data = {'error': str(relational_error)}
            relational_data_valid = False

        # Fetch data from TimescaleDB
        try:
            timescale_data = fetch_timescale_data(table_name)
            timescale_data_valid = True
        except Exception as timescale_error:
            timescale_data = []
            timescale_data_valid = False

        # Combine the data
        combined_data = {
            'relational_data': relational_data,
            'timescale_data': timescale_data
        }

        # Print messages based on data validity
        if relational_data_valid and timescale_data_valid:
            print("Both relational and Timescale data fetched successfully.")
        elif relational_data_valid:
            print("Relational data fetched successfully. Timescale data is invalid.")
        elif timescale_data_valid:
            print("Timescale data fetched successfully. Relational data is invalid.")
        else:
            print("No data from both databases.")

        # Return the combined data as JSON
        return jsonify({'data': combined_data})

    except Exception as e:
        return jsonify({'error': str(e)})

@main_bp.route('/save_threshold', methods=['POST'])
def save_threshold():
    data = request.get_json()
    print('Received Data:', data)  # Debugging line
    if not data:
        return jsonify({"message": "Invalid data"}), 400

    settings_file = os.path.join('mqtt_dashboard/settings', 'threshold_settings.json')
    print('Settings file path:', settings_file)  # Debugging line

    try:
        # Read existing settings
        if os.path.exists(settings_file):
            with open(settings_file, 'r') as file:
                settings = json.load(file)
        else:
            settings = {}

        # Extract the station-specific data
        stations = data['station'].split(', ')
        sensorSettings = data['sensorSettings']
        lowThreshold = data['lowThreshold']
        highThreshold = data['highThreshold']
        timeDelay = data['timeDelay']

        # Update the settings for each specified station
        for station in stations:
            settings[station] = {
                'sensorSettings': sensorSettings,
                'lowThreshold': lowThreshold,
                'highThreshold': highThreshold,
                'timeDelay': timeDelay
            }

        # Write the updated settings back to the file
        with open(settings_file, 'w') as file:
            json.dump(settings, file, indent=4)  # Use indent for better readability
        print('Data written to file successfully')  # Debugging line

        return jsonify({"message": "Threshold set successfully"})
    except Exception as e:
        print('Error:', e)
        return jsonify({"message": "Error saving threshold settings"}), 500
    

@main_bp.route('/get_threshold_settings', methods=['GET'])
def get_threshold_settings():
    settings_file = os.path.join('mqtt_dashboard/settings', 'threshold_settings.json')
    print('Settings file path:', settings_file)  # Debugging line

    try:
        if os.path.exists(settings_file):
            with open(settings_file, 'r') as file:
                settings = json.load(file)
            return jsonify(settings)
        else:
            return jsonify({}), 200
    except Exception as e:
        print('Error:', e)
        return jsonify({"message": "Error reading threshold settings"}), 500
    

@main_bp.route('/groups_with_topics', methods=['GET'])
def get_groups_with_topics():
    result = {}
    groups = db.session.query(models.group).all()
    for grp in groups:
        topics = db.session.query(models.timestream_table).filter_by(groupID=grp.groupID).all()
        result[grp.name] = [f"st_{t.station_id}" if t.station_id else t.topic.replace('/', '_') for t in topics]
    return jsonify(result)




    
# Data Fetching Routes for Google Maps Integration 
# ---------------------------------------------------
    
# Standard User Relational Database Fetch
    
@main_bp.route("/standard_user", methods=["GET"])
@login_required
def standard_user():
    try:
        # Get the list of tables based on the user's permissions
        user_id = current_user.userID
        table_ids = [p.tableID for p in current_user.permissions if p.type == "TOPIC" and p.tableID]

        # Create a list of table names from the table IDs, replacing "/" with "_"
        tables = []
        missing_table_ids = []
        for table_id in table_ids:
            table = db.session.query(models.timestream_table).filter(
                models.timestream_table.tableID == table_id
            ).first()
            if not table:
                missing_table_ids.append(table_id)
                continue
            tables.append(str(table.tableID))

        current_app.logger.info(
            "standard_user tables: user_id=%s table_ids=%s missing_ids=%s total=%s",
            user_id,
            table_ids,
            missing_table_ids,
            len(tables),
        )

        # Return the list of table names as JSON
        return jsonify({'tables': tables, 'missing_table_ids': missing_table_ids})

    except Exception as e:
        # Return a JSON error message
        return jsonify({'error': str(e)}), 500
    

# Group User Relational Database Fetch 

@main_bp.route("/group_user", methods=["GET"])
@login_required
def group_user():
    try:
        # Fetch all group_ids associated with the user
        user_group_ids = [p.groupID for p in current_user.permissions if p.type == "GROUP" and p.groupID]

        # Ensure that we fetch tables that are within the user's group permissions
        tables_in_groups = []
        if user_group_ids:
            tables_in_groups = db.session.query(models.timestream_table).filter(
                models.timestream_table.groupID.in_(user_group_ids)
            ).all()

        # Create a list of table IDs from the tables
        tables = [str(table.tableID) for table in tables_in_groups]

        current_app.logger.info(
            "group_user tables: user_id=%s group_ids=%s total=%s",
            current_user.userID,
            user_group_ids,
            len(tables),
        )

        # Return the list of table names as JSON
        return jsonify({'tables': tables, 'group_ids': user_group_ids})

    except Exception as e:
        # Return a JSON error message
        return jsonify({'error': str(e)}), 500


# Admin User Relational Database Fetch 

    
@main_bp.route("/admin_user_data", methods=["GET"])
@login_required
def admin_get_users_tables():
    if not is_admin(current_user):
        return jsonify({'error': 'Access denied. Only admins can access this route.'}), 403

    try:
        # Get all users
        users = db.session.query(models.User).all()

        user_tables = {}

        for user in users:
            # Get the list of tables for this user
            table_ids = [p.tableID for p in user.permissions if p.type == "TOPIC"]
            table_info = []

            for table_id in table_ids:
                table = db.session.query(models.timestream_table).filter(models.timestream_table.tableID == table_id).first()
                if not table:
                    print(table_id)
                    continue

                table_name = f"st_{table.station_id}" if table.station_id else table.topic.replace("/", "_")
                longitude = table.longitude
                latitude = table.latitude
                topic_id = table.tableID

                # Fetch additional attributes from the associated group
                group_id = table.groupID  # Assuming this is the foreign key to the group table
                group = db.session.query(models.group).filter(models.group.groupID == group_id).first()
                
                if group:
                    group_name = group.name
                else:
                    group_name = None  # If the group isn't found for some reason

                table_info.append({
                    'name': table_name,
                    'longitude': longitude,
                    'latitude': latitude,
                    'topic': table.topic,
                    'topic_id': topic_id,
                    'group_id': group_id,
                    'group_name': group_name,
                })

            user_tables[user.name] = table_info

        # Return the user tables as JSON
        return jsonify({'data': user_tables})

    except Exception as e:
        return jsonify({'error': str(e)})

# Admin User Relational Database Fetch 

@main_bp.route("/admin_user")
@login_required
def admin_user():
    try:
        # Get the name of the logged-in user
        user_name = current_user.name if current_user.is_authenticated else None

        # Pass the logged-in user's name to the template
        return render_template("admin_user.html", user_name=user_name)
    
    except Exception as e:
            return jsonify({'error': str(e)})
    


    
@main_bp.route("/sub_admin")
@login_required
def sub_admin():
    if(not is_admin(current_user)):
      return redirect(url_for('main.main'))
   
    us=db.session.query(models.User)

    users=[]
    tables=[]
    groups=[]
    for u in us:
        users.append({"id":u.userID,"name":u.name,"email":u.email})

    ts=db.session.query(models.timestream_table)

    for t in ts:
        tables.append({"id":t.tableID,"topic":t.topic})

    gs=db.session.query(models.group)

    for g in gs:
        groups.append({"id":g.groupID,"group":g.name})

    return render_template('company_admin.html',users=users, tables=tables,groups=groups)




    
    

# Technical User Relational Database Fetch
    
@main_bp.route("/get_all_tables", methods=["GET"])
def get_all_tables():
    try:

        if not is_technician(current_user):
            return jsonify({'error': 'Access denied. Only admins can access this route.'}), 403

        # Create a list of table IDs for all tables
        tables = [str(t.tableID) for t in models.timestream_table.query.all()]

        # Return the table names as JSON
        return jsonify({'tables': tables})

    except Exception as e:
        return jsonify({'error': str(e)})
    

@main_bp.route("/airport_data_fetch", methods=["GET"])
def airport_data_fetch():
    try:
        # Define the measurements you want to query
        measure_names = [
            "QFE_Avg",
            "QNH_Avg",
            "WSpd_Avg",
            "WDirMag_Avg",
            "BPress_Avg",
            "AirTemp_Avg",
            "RH",
            "DewPointTemp_Avg",
            "Rain_1h_RunTot",
            "Rain_12h_RunTot",
            "SkyVUE_FirstLayerCloudAmount",
            "SkyVUE_FirstLayerCloudHeight",
            "SkyVUE_SecondLayerCloudAmount",
            "SkyVUE_SecondLayerCloudHeight",
            "SkyVUE_ThirdLayerCloudAmount",
            "SkyVUE_ThirdLayerCloudHeight",
            "StationID",
        ]

        table_name = "CSAf_southafrica_Limpopo_SHA_Aviation_SHA_AWOS_6240_data_cr1000x_56192_Table2m"
        data = fetch_timescale_data(
            table_name,
            measure_names=measure_names,
            since_minutes=15,
            limit=None,
        )

        # Return the extracted data
        return jsonify(data)

    except Exception as e:
        return jsonify({'error': str(e)})


    except Exception as e:
        return jsonify({'error': str(e)})
    
@main_bp.route("/station_time/<string:table_name>", methods=["GET"])
def station_time(table_name):
    try:
        data = fetch_timescale_data(table_name, limit=1)

        # Return the extracted data
        return jsonify(data)

    except Exception as e:
        return jsonify({'error': str(e)}), 500
    
@main_bp.route("/airport_data_fetch_10m", methods=["GET"])
def airport_data_fetch_10m():
    try:
        # Define the measurements you want to query
        measure_names = ["WSpd_Avg", "WDir_Avg", "AirTemp_Avg", "QFE_Avg", "WSpd_Max"]

        table_name = "CSAf_southafrica_Limpopo_SHA_Aviation_SHA_AWOS_6240_data_cr1000x_56192"
        data = fetch_timescale_data(
            table_name,
            measure_names=measure_names,
            limit=28,
        )

        # Return the extracted data
        return jsonify(data)

    except Exception as e:
        return jsonify({'error': str(e)})
    
@main_bp.route("/airport_ui")
@login_required
def airport_ui():
    try:
        # Get the name of the logged-in user
        user_name = current_user.name if current_user.is_authenticated else None

        # Pass the logged-in user's name to the template
        return render_template("wind-barb.html", user_name=user_name)
    
    except Exception as e:
            return jsonify({'error': str(e)})
    

@main_bp.route("/geoss_stations")
@login_required
def geoss_stations():
    try:
        # Get the name of the logged-in user
        user_name = current_user.name if current_user.is_authenticated else None

        # Pass the logged-in user's name to the template
        return render_template("geoss_stations.html", user_name=user_name)
    
    except Exception as e:
            return jsonify({'error': str(e)})
    
    

@main_bp.route("/threshold_settings")
@login_required
def threshold_settings():
    try:
        # Get the name of the logged-in user
        user_name = current_user.name if current_user.is_authenticated else None

        # Pass the logged-in user's name to the template
        return render_template("group_accordion.html", user_name=user_name)
    
    except Exception as e:
            return jsonify({'error': str(e)})
    
@main_bp.route("/ekland_ui")

def ekland_ui():
    try:
        # Get the name of the logged-in user
        user_name = current_user.name if current_user.is_authenticated else None

        # Pass the logged-in user's name to the template
        return render_template("layout.html", user_name=user_name)
    
    except Exception as e:
            return jsonify({'error': str(e)})
    
@main_bp.route("/ekland_pwa")

def ekland_pwa():
    try:
        # Get the name of the logged-in user
        user_name = current_user.name if current_user.is_authenticated else None

        # Pass the logged-in user's name to the template
        return render_template("ekland_pwa.html", user_name=user_name)
    
    except Exception as e:
            return jsonify({'error': str(e)})
    

#@main_bp.after_request
#def set_csp(response):
#    response.headers['Content-Security-Policy'] = (
#        "default-src 'self'; "
#        "script-src 'self' 'https://apis.google.com'; "
#    )
#    return response
    



@main_bp.route('/pwa')
def serve_index():
    return send_file('static/pwa/index.html')    
    
@main_bp.route("/topic_stations", methods=['GET'])
@login_required
def topic_stations():
    if not is_admin(current_user):
        return jsonify({"error": "Unauthorized"}), 403

    ts = db.session.query(models.timestream_table)

    topics = []
    for t in ts:
        topics.append({"id": t.tableID, "topic": t.topic, "group": t.groupID})

    return jsonify({"topics": topics})
    







@main_bp.route("/topic/<tid>")
@login_required
def topic(tid):
    # Fetch the topic from the database
    t = db.session.query(models.timestream_table).filter(models.timestream_table.tableID == tid).first()
    if t is None:
        return redirect(url_for('main.main'))

    # Fetch all group_ids associated with the user
    user_group_ids = [p.groupID for p in current_user.permissions if p.type == "GROUP"]

    # Initialize has_permission as False
    has_permission = False

    # Check if the table's groupID is in the user's group_ids
    if t.groupID in user_group_ids:
        has_permission = True

    # Check other permissions (topic and all_topic permissions)
    for p in current_user.permissions:
        if (p.type == "TOPIC" and str(p.tableID) == tid) or p.type == "ALL_TOPIC":
            has_permission = True
            break

    if not has_permission:
        return redirect(url_for('main.main'))

    # The rest of your function follows...
    dbs = get_dbs()
    id = t.station_id if t.station_id else re.split("/", t.topic)[-1]
    
    # Use live dashboard instead of snapshot for dynamic data querying
    # Include time range to ensure data visibility
    # Use proxy to avoid external port access issues
    dashboard_url = f'/grafana/d/{t.db_uid}?kiosk=tv&orgId=1&from=now-24h&to=now&refresh=30s'
    
    current_app.logger.info(
        "Rendering topic view: tableID=%s topic=%s grafana_dashboard=%s",
        t.tableID,
        t.topic,
        t.db_uid,
    )
    return render_template('index.html', name=current_user.name, url=dashboard_url, dbs=dbs, long=t.longitude, lat=t.latitude, showPos=True, ID=id, is_admin=is_admin(current_user))


@main_bp.route('/grafana/<path:path>', methods=['GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'OPTIONS'])
@login_required
def grafana_proxy(path):
    """Proxy requests to Grafana running on localhost"""
    try:
        # Build the full URL to local Grafana instance
        url = f'http://127.0.0.1:3000/grafana/{path}'
        if request.query_string:
            url += '?' + request.query_string.decode('utf-8')
        
        # Prepare headers to forward
        headers = {k: v for k, v in request.headers if k.lower() not in ['host', 'cookie', 'content-length']}
        
        # Forward the request to Grafana with appropriate method
        resp = requests.request(
            method=request.method,
            url=url,
            headers=headers,
            data=request.get_data(),
            cookies=request.cookies,
            allow_redirects=False,
            stream=False,
            timeout=30
        )
        
        # Create response with proxied content
        from flask import Response
        excluded_headers = ['content-encoding', 'content-length', 'transfer-encoding', 'connection',
                            'x-frame-options', 'content-security-policy']
        response_headers = [(name, value) for (name, value) in resp.headers.items()
                           if name.lower() not in excluded_headers]

        content = resp.content
        content_type = resp.headers.get('content-type', '')

        # Rewrite Grafana's absolute internal URLs so the browser sends API calls
        # back through this proxy rather than directly to localhost:3000 (unreachable).
        if any(t in content_type for t in ('text/', 'application/json', 'application/javascript')):
            try:
                text = content.decode('utf-8')
                text = text.replace('http://localhost:3000', '')
                text = text.replace('http:\\/\\/localhost:3000', '')
                content = text.encode('utf-8')
            except Exception:
                pass

        return Response(content, resp.status_code, response_headers)
    except Exception as e:
        current_app.logger.error(f"Grafana proxy error: {e}")
        return f"Error connecting to Grafana: {str(e)}", 502


@main_bp.route('/group/<gid>')
@login_required
def group(gid):
    dbs=get_dbs()
    g=db.session.query(models.group).filter(models.group.groupID==gid)
    if(g.count()==0):
        return redirect(url_for('main.main'))
    has_permission=False
    for p in current_user.permissions:
        if (p.type=="GROUP" and str(p.groupID)==gid) or p.type=="ALL_TOPIC" or p.type=="ADMIN":
            has_permission=true
            break
    g=g.first()

    ts=db.session.query(models.timestream_table).filter(models.timestream_table.groupID==gid)
    tsx=[]
    for t in ts:
        tsx.append({'id':t.tableID,'topic':t.topic})
    

    return render_template('group.html',group=g.name,dbs=dbs,ts=tsx,is_admin=is_admin(current_user))


@main_bp.route("/admin")
@login_required
def admin():
    if(not is_admin(current_user)):
        return redirect(url_for('main.main'))

    us=db.session.query(models.User)

    users=[]
    tables=[]
    groups=[]
    for u in us:
        users.append({"id":u.userID,"name":u.name,"email":u.email})

    ts=db.session.query(models.timestream_table)

    for t in ts:
        tables.append({"id":t.tableID,"topic":t.topic})

    gs=db.session.query(models.group)

    for g in gs:
        groups.append({"id":g.groupID,"group":g.name})

    return render_template('admin.html',users=users, tables=tables,groups=groups)


@main_bp.route("/admin_v2")
@login_required
def admin_v2():
    if(not is_admin(current_user)):
        return redirect(url_for('main.main'))

    us=db.session.query(models.User)

    users=[]
    tables=[]
    groups=[]
    for u in us:
        users.append({"id":u.userID,"name":u.name,"email":u.email})

    ts=db.session.query(models.timestream_table)

    for t in ts:
        tables.append({"id":t.tableID,"topic":t.topic})

    gs=db.session.query(models.group)

    for g in gs:
        groups.append({"id":g.groupID,"group":g.name})

    return render_template('admin-official.html',users=users, tables=tables,groups=groups)



@main_bp.route("/admin_endpoint")
@login_required
def admin_endpoint():
    if not is_admin(current_user):
        return jsonify({"error": "Unauthorized"}), 403

    users = []
    for user in models.User.query.all():
        user_data = {"id": user.userID, "name": user.name, "email": user.email}
        user_data["groups"] = [{"id": group.groupID, "name": group.name} for group in user.groups]
        users.append(user_data)

    tables = [{"id": t.tableID, "topic": t.topic} for t in models.timestream_table.query.all()]
    groups = [{"id": g.groupID, "name": g.name} for g in models.group.query.all()]

    return jsonify({"users": users, "tables": tables, "groups": groups})




# Group Admin User Route 

@main_bp.route("/group_admin_route")
@login_required
def group_admin_route():
    try:
        # Get the group ID of the logged-in user
        group_id = None
        group_name = None
        if current_user.is_authenticated:
            user_permissions = current_user.permissions
            for permission in user_permissions:
                if permission.groupID:
                    group_id = permission.groupID
                    break

        # Get the username of the current user
        user_name = current_user.name if current_user.is_authenticated else None

        # Return the data as JSON
        return jsonify({'group_id': group_id, 'user_name': user_name})

    except Exception as e:
        return jsonify({'error': str(e)}) 









@main_bp.route("/admin_group_data", methods=["GET"])
@login_required
def admin_group_data():
   

    try:
        # Get all users
        users = db.session.query(models.User).all()

        user_info = {}

        for user in users:
            first_permission = db.session.query(models.permission).filter(models.permission.userID == user.userID).first()
            if first_permission:
                group = db.session.query(models.group).filter(models.group.groupID == first_permission.groupID).first()
                if group:
                    group_name = group.name
                    group_id = group.groupID
                else:
                    group_name = None
                    group_id = None

                user_info[user.email] = {
                    'id': user.userID,
                    'name': user.name,
                    'permission_type': first_permission.type,
                    'group_id': group_id,
                    'group_name': group_name,
                }

        # Return the user info as JSON
        return jsonify({'data': user_info})

    except Exception as e:
        return jsonify({'error': str(e)})












@main_bp.route("/dashboard_admin")
@login_required
def dashboard_admin():
    if(not is_admin(current_user)):
        return redirect(url_for('main.main'))

    tables=[]
    ts=db.session.query(models.timestream_table)

    for t in ts:
        tables.append({"id":t.tableID,"topic":t.topic})

    return render_template('dashboard_admin.html',tables=tables)

@main_bp.route("/broker_admin")
@login_required
def broker_admin():
    if(not is_admin(current_user)):
        return redirect(url_for('main.main'))

    brokers=[]
    bs=db.session.query(models.broker)

    for b in bs:
        brokers.append({"id":b.brokerID,"name":b.name,"URL":b.URL,"username":b.username,"password":b.password,"port":b.port})

    return render_template('broker_admin.html',brokers=brokers)

@main_bp.route("/group_admin")
@login_required
def group_admin():
    if(not is_admin(current_user)):
        return redirect(url_for('main.main'))

    us=db.session.query(models.User)

    users=[]
    tables=[]
    groups=[]
    for u in us:
        users.append({"id":u.userID,"name":u.name,"email":u.email})

    ts=db.session.query(models.timestream_table)

    for t in ts:
        tables.append({"id":t.tableID,"topic":t.topic})

    gs=db.session.query(models.group)

    for g in gs:
        groups.append({"id":g.groupID,"group":g.name})

    return render_template('group_admin.html',users=users, tables=tables,groups=groups)

@main_bp.route("/search",methods=["POST"])
@login_required
def search():
    if(not is_admin(current_user)):
        return {"users":"none"}
    searchval=request.get_json().get("searchval")
    users=[]
    ids=[]
    us=db.session.query(models.User).filter(models.User.email.contains(searchval))

    for u in us:
        users.append({"id":u.userID,"name":u.name,"email":u.email})
        ids.append(u.userID)

    us=db.session.query(models.User).filter(models.User.name.contains(searchval))

    for u in us:
        if(u.userID not in ids):
            users.append({"id":u.userID,"name":u.name,"email":u.email})

    return {"users":users}

@main_bp.route("/search_brokers",methods=["POST"])
@login_required
def search_brokers():
    if(not is_admin(current_user)):
        return {"brokers":"none"}
    searchval=request.get_json().get("searchval")
    brokers=[]
    ids=[]
    bs=db.session.query(models.broker).filter(models.broker.URL.contains(searchval))

    for b in bs:
        brokers.append({"id":b.brokerID,"name":b.name,"URL":b.URL,"username":b.username,"password":b.password,"port":b.port})
        ids.append(b.brokerID)

    bs=db.session.query(models.broker).filter(models.broker.name.contains(searchval))

    for b in bs:
        if(b.brokerID not in ids):
            brokers.append({"id":b.brokerID,"name":b.name,"URL":b.URL,"username":b.username,"password":b.password,"port":b.port})

    return {"brokers":brokers}

@main_bp.route("/perms",methods=["POST"])
@login_required
def get_perms():
    if(not is_admin(current_user)):
        return {"perms":"none"}
    searchval=request.get_json().get("searchval")
    perms=[]
    ps=db.session.query(models.permission).filter(models.permission.userID==searchval)
    group="None"
    for p in ps:
        if(not p.tableID):
            table="None"
        else:
            try:
                table=db.session.query(models.timestream_table).filter(models.timestream_table.tableID==p.tableID).first().topic
            except:
                table="None"
        if(p.groupID==0):
            group="None"
        else:
            group=str(p.groupID)
        perms.append({"id":p.permissionID,"type":p.type,"table":table,"group":group})
    return {"perms":perms}

@main_bp.route("/unadded",methods=["POST"])
@login_required
def unadded():
    if(not is_admin(current_user)):
        return {"perms":"none"}
    unadded=[]
    ts=db.session.query(models.timestream_table).filter((models.timestream_table.groupID==0) | (models.timestream_table.groupID==None))
    for t in ts:
        unadded.append({"id":t.tableID,"topic":t.topic})
    return {"unadded":unadded}

@main_bp.route("/added",methods=["POST"])
@login_required
def added():
    if(not is_admin(current_user)):
        return {"perms":"none"}
    added=[]
    searchval=request.get_json().get("searchval")
    ts=db.session.query(models.timestream_table).filter(models.timestream_table.groupID==searchval)
    for t in ts:
        added.append({"id":t.tableID,"topic":t.topic})
    return {"added":added}

@main_bp.route("/remove_table_from_group",methods=["POST"])
@login_required
def remove_table_from_group():
    if(not is_admin(current_user)):
        return {"perms":"none"}
    added=[]
    tableID=request.get_json().get("tableID")
    ts=models.timestream_table.query.filter(models.timestream_table.tableID==tableID).first()
    ts.groupID=0
    db.session.commit()
    return {"success":added}

@main_bp.route("/add_table_to_group",methods=["POST"])
@login_required
def add_table_to_group():
    if(not is_admin(current_user)):
        return {"perms":"none"}
    added=[]
    tableID=request.get_json().get("tableID")
    groupID=request.get_json().get("groupID")
    ts=models.timestream_table.query.filter(models.timestream_table.tableID==tableID).first()
    ts.groupID=groupID
    db.session.commit()
    return {"success":added}

@main_bp.route("/create_group",methods=["POST"])
@login_required
def create_group():
    if(not is_admin(current_user)):
        return {"status":"fail"}
    try:
        name=request.get_json().get("name")

        new_group=models.group(name=name)

        db.session.add(new_group)
        db.session.commit()

        return {"status":"success"}
    except:
        return {"status":"fail"}

@main_bp.route("/delete_group",methods=["POST"])
@login_required
def delete_group():
    if(not is_admin(current_user)):
        return {"status":"fail"}
    try:
        groupID=request.get_json().get("groupID")

        tables=models.timestream_table.query.filter(models.timestream_table.groupID == groupID)
        for t in tables:
            t.groupID=0
        

        models.permission.query.filter(models.permission.groupID==groupID).delete()
        models.group.query.filter(models.group.groupID==groupID).delete()
        
        db.session.commit()

        return {"status":"success"}
    except:
        return {"status":"fail"}

@main_bp.route("/groups",methods=["POST"])
@login_required
def groups():
    if(not is_admin(current_user)):
        return {"perms":"none"}
    groups=[]
    gs=db.session.query(models.group)
    for g in gs:
        groups.append({"id":g.groupID,"name":g.name})
    return {"groups":groups}

@main_bp.route("/create_user",methods=["POST"])
@login_required
def create_user():
    if(not is_admin(current_user)):
        return {"status":"fail"}
    try:
        email=request.get_json().get("email")
        name=request.get_json().get("name")
        password=request.get_json().get("password")

        user=User.query.filter_by(email=email).first()
        if user:
            return {"status":"fail"}
        new_user=User(email=email,name=name,password=generate_password_hash(password, method='sha256'))

        db.session.add(new_user)
        db.session.commit()

        return {"status":"success"}
    except:
        return {"status":"fail"}

@main_bp.route("/create_broker",methods=["POST"])
@login_required
def create_broker():
    if(not is_admin(current_user)):
        return {"status":"fail"}
    try:
        payload = request.get_json() or {}
        name=payload.get("name")
        port=payload.get("port")
        URL=payload.get("URL")
        username=payload.get("username")
        password=payload.get("password")

        if not name or not URL or not port:
            return {"status":"fail","error":"Missing required fields: name, URL, port"}

        try:
            port = int(port)
        except (TypeError, ValueError):
            return {"status":"fail","error":"Invalid port; must be an integer"}

        authentication=0 if ((username or "")=="" or (password or "")=="") else 1

        new_broker=models.broker(name=name,port=port,URL=URL,username=username,password=password,authentication=authentication)

        db.session.add(new_broker)
        db.session.commit()

        return {"status":"success"}
    except Exception as exc:
        current_app.logger.exception("create_broker failed (payload=%s): %s", payload, exc)
        db.session.rollback()
        return {"status":"fail","error":str(exc)}

@main_bp.route("/delete_user",methods=["POST"])
@login_required
def delete_user():
    if(not is_admin(current_user)):
        return {"status":"fail"}
    try:
        userID=request.get_json().get("id")

        if(userID==current_user.userID):
            return {"status":"fail"}

        models.permission.query.filter(models.permission.userID == userID).delete()
        models.User.query.filter(models.User.userID == userID).delete()
        db.session.commit()

        return {"status":"success"}
    except:
        return {"status":"fail"}

@main_bp.route("/delete_perm",methods=["POST"])
@login_required
def delete_perm():
    if(not is_admin(current_user)):
        return {"status":"fail"}
    try:
        permID=request.get_json().get("id")
        models.permission.query.filter(models.permission.permissionID==permID).delete()
        db.session.commit()
        return {"status":"success"}
    except:
        return {"status":"fail"}

@main_bp.route("/delete_broker",methods=["POST"])
@login_required
def delete_broker():
    if(not is_admin(current_user)):
        return {"status":"fail"}
    try:
        brokerID=request.get_json().get("id")
        print(brokerID)
        models.broker.query.filter(models.broker.brokerID==brokerID).delete()
        db.session.commit()
        return {"status":"success"}
    except:
        return {"status":"fail"}

@main_bp.route("/add_perm",methods=["POST"])
@login_required
def add_perm():
    print('add perm')
    if(not is_admin(current_user)):
        return {"status":"fail"}
    try:
        userID=request.get_json().get("id")
        type=request.get_json().get("type")
        tableID=request.get_json().get("table")
        groupID=request.get_json().get("group")
        if(tableID==-1):
            new_perm=models.permission(userID=userID,type=type,groupID=groupID)
        else:
            new_perm=models.permission(userID=userID,type=type,tableID=tableID,groupID=groupID)
        db.session.add(new_perm)
        db.session.commit()
        return {"status":"success"}
    except:
        return {"status":"fail"}

@main_bp.route("/remove_perm",methods=["POST"])
@login_required
def remove_perm():
    if(not is_admin(current_user)):
        return {"status":"fail"}
    try:
        permID=request.get_json().get("id")
        if(permID==-1):
            return {"status":"fail"}
        models.permission.query.filter(models.permission.permissionID==permID).delete()
        db.session.commit()
        return {"status":"success"}
    except:
        print("fail")
        return {"status":"fail"}
    

@main_bp.route('/update_user', methods=['POST'])
@login_required
def update_user():
    # Check if the current user is allowed to update user information
    # This depends on your application's authorization logic
    # For example, let's assume only admins or the users themselves can update their info:
    if not current_user.is_admin:
        return jsonify({'status': 'fail', 'message': 'Unauthorized access'}), 403

    data = request.json
    user_id = data.get('id')
    user = User.query.get(user_id)

    if user:
        # Update user fields if provided in the request
        user.name = data.get('name', user.name)  # Update name if provided
        user.email = data.get('email', user.email)  # Update email if provided
        # Update the password only if a new one is provided
        if 'password' in data and data['password']:
            user.password = generate_password_hash(data['password'], method='sha256')

        # Commit changes to the database
        try:
            db.session.commit()
            return jsonify({'status': 'success', 'message': 'User updated successfully'}), 200
        except Exception as e:  # Catch exceptions related to database operations
            db.session.rollback()  # Rollback the transaction on error
            return jsonify({'status': 'fail', 'message': 'Database error: ' + str(e)}), 500
    else:
        return jsonify({'status': 'fail', 'message': 'User not found'}), 404




@main_bp.route("/remove_topic",methods=["POST"])
@login_required
def remove_topic():
    if(not is_admin(current_user)):
        return {"status":"fail"}
    topicID=request.get_json().get("id")
    grafana_helpers.delete_dashboard_table(models.timestream_table.query.filter(models.timestream_table.tableID==topicID).first())
    models.permission.query.filter(models.permission.tableID==topicID).delete()
    models.timestream_measurement.query.filter(models.timestream_measurement.tableID==topicID).delete()
    models.timestream_table.query.filter(models.timestream_table.tableID==topicID).delete()
    db.session.commit()
    return {"status":"success"}
@main_bp.route("/measurements",methods=["POST"])
@login_required
def get_meas():
    if(not is_admin(current_user)):
        return {"perms":"none"}
    searchval=request.get_json().get("searchval")
    meas=[]
    ms=db.session.query(models.timestream_measurement).filter(models.timestream_measurement.tableID==searchval)

    for m in ms:
        meas.append({"id":m.measurementID,"meas":m.name,"nickname":m.nickname,"direction":m.directionName,"visible":m.visible,"status":m.status,"graph":m.graph})
    return {"meas":meas}

@main_bp.route("/edit_measurement",methods=["POST"])
@login_required
def edit_meas():
    if(not is_admin(current_user)):
        return {"status":"fail"}
    id=request.get_json().get("id")
    nickname=request.get_json().get("nickname")
    visible=request.get_json().get("visible")
    status=request.get_json().get("status")
    direction=request.get_json().get("direction")
    graph=request.get_json().get("graph")
    

    ms=db.session.query(models.timestream_measurement).filter(models.timestream_measurement.measurementID==id).first()
    t=db.session.query(models.timestream_table).filter(models.timestream_table.tableID==ms.tableID).first()
    def normalize_flag(value):
        if value is None:
            return None
        if isinstance(value, bool):
            return 1 if value else 0
        if isinstance(value, (int, float)):
            return 1 if value else 0
        value_str = str(value).strip().lower()
        if value_str in {"true", "1", "yes", "y", "on"}:
            return 1
        if value_str in {"false", "0", "no", "n", "off"}:
            return 0
        return None

    ms.nickname=nickname
    normalized_visible = normalize_flag(visible)
    normalized_status = normalize_flag(status)
    if normalized_visible is not None:
        ms.visible=normalized_visible
    if normalized_status is not None:
        ms.status=normalized_status
    ms.graph=graph

    if(direction):
        ms.directionName=direction

    db.session.commit()
    grafana_helpers.create_dashboard_table(t)

    return {"status":"success"}

@main_bp.route("/edit_broker",methods=["POST"])
@login_required
def edit_broker():
    edited=False
    if(not is_admin(current_user)):
        return {"status":"fail"}
    id=request.get_json().get("id")
    name=request.get_json().get("name")
    URL=request.get_json().get("URL")
    port=request.get_json().get("port")
    username=request.get_json().get("username")
    password=request.get_json().get("password")

    b=db.session.query(models.broker).filter(models.broker.brokerID==id).first()
    
    if(b.URL!=URL or b.port!=port or b.username!=username or b.password!=password):
        edited=True
    b.URL=URL
    b.port=port
    b.name=name

    if(username=="" or password==""):
        b.authentication=False
    b.username=username
    b.password=password

    db.session.commit()

    if(edited):
        messages[1]=id
        messages[2]='E'
        messages[0]=edited
        
    return {"status":"success"}

@main_bp.route("/topics",methods=["POST"])
@login_required
def get_topics():
    if(not is_admin(current_user)):
        return {"status":"fail"}
    ts=db.session.query(models.timestream_table)
    tables=[]
    for t in ts:
        tables.append({"id":t.tableID,"topic":t.topic})
    return{"tables":tables}