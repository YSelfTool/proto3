#!/usr/bin/env python3
import locale
locale.setlocale(locale.LC_TIME, "de_DE.utf8")

from flask import Flask, g, current_app, request, session, flash, redirect, url_for, abort, render_template, Response
from flask_script import Manager, prompt
from flask_migrate import Migrate, MigrateCommand
#from flask_socketio import SocketIO
from celery import Celery
from functools import wraps

import config
from shared import db, date_filter, datetime_filter, ldap_manager, security_manager
from utils import is_past, mail_manager, url_manager
from models.database import ProtocolType, Protocol, DefaultTOP, TOP, Document, Todo, Decision, MeetingReminder, Error
from views.forms import LoginForm
from views.tables import ProtocolsTable

app = Flask(__name__)
app.config.from_object(config)
db.init_app(app)
migrate = Migrate(app, db)
manager = Manager(app)
manager.add_command("db", MigrateCommand)

def make_celery(app, config):
    celery = Celery(app.import_name, broker=config.CELERY_BROKER_URL)
    celery.conf.update(app.config)
    return celery
celery = make_celery(app, config)

#def make_socketio(app, config):
#    socketio = SocketIO(app)
#    return socketio
#socketio = make_socketio(app, config)

app.jinja_env.trim_blocks = True
app.jinja_env.lstrip_blocks = True
app.jinja_env.filters["datify"] = date_filter
app.jinja_env.filters["datetimify"] = datetime_filter
app.jinja_env.filters["url_complete"] = url_manager.complete
app.jinja_env.tests["auth_valid"] = security_manager.check_user

import tasks

from auth import User

def check_login():
    return "auth" in session and security_manager.check_user(session["auth"])
def current_user():
    if not check_login():
        return None
    return User.from_hashstring(session["auth"])

def login_required(function):
    @wraps(function)
    def decorated_function(*args, **kwargs):
        if check_login():
            return function(*args, **kwargs)
        else:
            return redirect(url_for("login", next=request.url))
    return decorated_function

app.jinja_env.globals.update(check_login=check_login)
app.jinja_env.globals.update(current_user=current_user)

# blueprints here

@app.route("/")
#@login_required
def index():
    return render_template("index.html")

@app.route("/protocol/list")
def list_protocols():
    is_logged_in = check_login()
    user = current_user()
    protocols = [
        protocol for protocol in Protocol.query.all()
        if (not is_logged_in and protocol.protocoltype.is_public)
        or (is_logged_in and (
            protocol.protocoltype.public_group in user.groups
            or protocol.protocoltype.private_group in user.groups))]
    protocols_table = ProtocolsTable(protocols)
    return render_template("protocol-list.html", protocols=protocols, protocols_table=protocols_table)
    

@app.route("/login", methods=["GET", "POST"])
def login():
    if "auth" in session:
        flash("You are already logged in.", "alert-success")
        return redirect(url_for(request.args.get("next") or "index"))
    form = LoginForm()
    if form.validate_on_submit():
        user = ldap_manager.login(form.username.data, form.password.data)
        if user is not None:
            session["auth"] = security_manager.hash_user(user)
            flash("Login successful, {}!".format(user.username), "alert-success")
            return redirect(request.args.get("next") or url_for("index"))
        else:
            flash("Wrong login data. Try again.", "alert-error")
    return render_template("login.html", form=form)

@app.route("/logout")
@login_required
def logout():
    if "auth" in session:
        session.pop("auth")
    else:
        flash("You are not logged in.", "alert-error")
    return redirect(url_for(".index"))


if __name__ == "__main__":
    manager.run()
