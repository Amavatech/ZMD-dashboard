from flask import Flask
from flask_login import LoginManager
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
import configparser,os
from multiprocessing import shared_memory
import logging
"""
Messages sent over the shared memory list to the mqtt subscriber script. 
The first element is a flag that gets sent when a new message is received.
The second element is the ID of the broker who's state is changed.
The third element is a character indicating the type of change that is made.
'X' for no change.
'N' for new broker.
'E' for edited broker.
'D' for deleted broker.
"""

script_dir=os.path.dirname(os.path.realpath(__file__))
#RUN WITH: python -m flask --app mqtt_dashboard --debug run
config=configparser.ConfigParser()
config.read(script_dir+'/config.ini')
api_base_url = config.get('App', 'ApiBaseUrl', fallback='').rstrip('/')

db=SQLAlchemy()
try:
    messages=shared_memory.ShareableList([False,int(-1),'X'],name="messages")
except FileExistsError:
    messages=shared_memory.ShareableList(name="messages")

print(messages)
def create_app():
    
    app=Flask(__name__)

    if not app.logger.handlers:
        stream_handler = logging.StreamHandler()
        stream_handler.setLevel(logging.INFO)
        formatter = logging.Formatter(
            "[%(asctime)s] %(levelname)s in %(module)s: %(message)s"
        )
        stream_handler.setFormatter(formatter)
        app.logger.addHandler(stream_handler)

    app.logger.setLevel(logging.INFO)

    @app.context_processor
    def inject_api_base_url():
        return {"api_base_url": api_base_url}

    CORS(
        app,
        resources={
            r"/*": {
                "origins": [
                    r"http://localhost(:\d+)?",
                    r"http://127\.0\.0\.1(:\d+)?",
                    r"https://localhost(:\d+)?",
                    r"https://127\.0\.0\.1(:\d+)?",
                    r"http://41\.72\.104\.142(:\d+)?",
                ]
            }
        },
        supports_credentials=True,
    )

    app.config['SECRET_KEY']=config['Flask']['Secret Key']
    schema_name = config['Timescale'].get('Schema', 'public')
    app.config['SQLALCHEMY_DATABASE_URI']=(
        f"postgresql+psycopg2://{config['Timescale']['UserName']}:{config['Timescale']['Password']}@"
        f"{config['Timescale']['Host']}:{config['Timescale']['Port']}/{config['Timescale']['DataBase']}"
        f"?options=-csearch_path%3D{schema_name}"
    )
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS']=False
    db.init_app(app)

    login_manager = LoginManager()
    login_manager.login_view='auth.login'
    login_manager.init_app(app)

    from .models import User
    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    from mqtt_dashboard.auth.auth import auth as auth_blueprint
    app.register_blueprint(auth_blueprint)

    from mqtt_dashboard.main.main import main_bp as main_blueprint
    app.register_blueprint(main_blueprint)
    print(messages)
    return app