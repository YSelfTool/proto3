#!/usr/bin/env python3
import locale
locale.setlocale(locale.LC_TIME, "de_DE.utf8")

from flask import Flask, g, current_app, request, session, flash, redirect, url_for, abort, render_template, Response
from flask_script import Manager, prompt
from flask_migrate import Migrate, MigrateCommand
#from flask_socketio import SocketIO
from celery import Celery

import config
from shared import db, date_filter, datetime_filter
from utils import is_past, mail_manager, url_manager

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

import tasks

# blueprints here

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/imprint/")
def imprint():
    return render_template("imprint.html")

@app.route("/contact/")
def contact():
    return render_template("contact.html")

@app.route("/privacy/")
def privacy():
    return render_template("privacy.html")

if __name__ == "__main__":
    manager.run()
