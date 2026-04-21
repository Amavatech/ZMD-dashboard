from flask import Blueprint, render_template, url_for, request, redirect, flash, current_app
from flask_login import login_required, login_user, logout_user
from werkzeug.security import generate_password_hash, check_password_hash
from mqtt_dashboard import db,grafana_helpers
from mqtt_dashboard.models import User

auth=Blueprint('auth',__name__, template_folder='../templates')

ADMIN_PERMISSION_TYPES = {
    "ADMIN",
    "GROUP_ADMIN",
    "GROUP_ADMI",
    "GADMIN",
    "GDMIN",
}


def is_admin_user(user: User) -> bool:
    for p in user.permissions:
        p_type = (p.type or "").upper()
        if p_type in ADMIN_PERMISSION_TYPES:
            return True
    return False

@auth.route('/login')
def login():
    return render_template('login.html')

@auth.route('/login', methods=['POST'])
def login_post():
    email=request.form.get('email')
    password=request.form.get('password')
    remember=True if request.form.get('remember') else False

    user=User.query.filter_by(email=email).first()

    if not user or not check_password_hash(user.password,password):
        flash('Please check your login details and try again.')
        return redirect(url_for('auth.login'))

    login_user(user,remember=remember)

    try:
        permissions = [p.type for p in user.permissions]
        current_app.logger.info(
            "User login: id=%s email=%s name=%s admin=%s permissions=%s",
            user.userID,
            user.email,
            user.name,
            is_admin_user(user),
            permissions,
        )
    except Exception as log_error:
        current_app.logger.warning("Failed to log user details: %s", log_error)

    return redirect(url_for('main.main'))

@auth.route('/signup')
def signup():
    return render_template('signup.html')

@auth.route('/signup',methods=['POST'])
def signup_post():
    print("Sign up POST triggered")

    email=request.form.get('email')
    name=request.form.get('name')
    password=request.form.get('password')

    user=User.query.filter_by(email=email).first()

    if user:
        flash('Email address already exists')
        return redirect(url_for('auth.signup'))

    new_user=User(email=email,name=name,password=generate_password_hash(password, method='sha256'))

    db.session.add(new_user)
    db.session.commit()
    grafana_helpers.create_dashboard_user(new_user)
    return redirect(url_for('auth.login'))

@auth.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('auth.login'))





