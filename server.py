#!/usr/bin/env python3
import locale
locale.setlocale(locale.LC_TIME, "de_DE.utf8")

from flask import Flask, g, current_app, request, session, flash, redirect, url_for, abort, render_template, Response, send_file
from werkzeug.utils import secure_filename
from flask_script import Manager, prompt
from flask_migrate import Migrate, MigrateCommand
#from flask_socketio import SocketIO
from celery import Celery
from functools import wraps
import requests
from io import StringIO, BytesIO
import os

import config
from shared import db, date_filter, datetime_filter, date_filter_long, time_filter, ldap_manager, security_manager
from utils import is_past, mail_manager, url_manager
from models.database import ProtocolType, Protocol, DefaultTOP, TOP, Document, Todo, Decision, MeetingReminder, Error
from views.forms import LoginForm, ProtocolTypeForm, DefaultTopForm, MeetingReminderForm, NewProtocolForm, DocumentUploadForm
from views.tables import ProtocolsTable, ProtocolTypesTable, ProtocolTypeTable, DefaultTOPsTable, MeetingRemindersTable, ErrorsTable, TodosTable, DocumentsTable

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
app.jinja_env.filters["timify"] = time_filter
app.jinja_env.filters["datify_long"] = date_filter_long
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

def group_required(function, group):
    @wraps(function)
    def decorated_function(*args, **kwargs):
        if group in current_user.groups:
            return function(*args, **kwargs)
        else:
            flash("You do not have the necessary permissions to view this page.")
            return redirect(request.args.get("next") or url_for("index"))
    return decorated_function

app.jinja_env.globals.update(check_login=check_login)
app.jinja_env.globals.update(current_user=current_user)
app.jinja_env.globals.update(zip=zip)

# blueprints here

@app.route("/")
def index():
    return render_template("index.html")

@login_required
@app.route("/types/list")
def list_types():
    is_logged_in = check_login()
    user = current_user()
    types = [
        protocoltype for protocoltype in ProtocolType.query.all()
        if (protocoltype.public_group in user.groups
        or protocoltype.private_group in user.groups
        or protocoltype.is_public)]
    types_table = ProtocolTypesTable(types)
    return render_template("types-list.html", types=types, types_table=types_table)

@app.route("/type/new", methods=["GET", "POST"])
@login_required
def new_type():
    form = ProtocolTypeForm()
    if form.validate_on_submit():
        user = current_user()
        if form.private_group.data not in user.groups:
            flash("Du kannst keinen internen Protokolltypen anlegen, zu dem du selbst keinen Zugang hast.", "alert-error")
        else:
            protocoltype = ProtocolType(form.name.data, form.short_name.data,
                form.organization.data, form.is_public.data,
                form.private_group.data, form.public_group.data,
                form.private_mail.data, form.public_mail.data)
            db.session.add(protocoltype)
            db.session.commit()
            flash("Der Protokolltyp {} wurde angelegt.".format(protocoltype.name), "alert-success")
        return redirect(request.args.get("next") or url_for("list_types"))
    return render_template("type-new.html", form=form)

@app.route("/type/edit/<int:type_id>", methods=["GET", "POST"])
@login_required
def edit_type(type_id):
    protocoltype = ProtocolType.query.filter_by(id=type_id).first()
    if protocoltype is None:
        flash("Dieser Protokolltyp existiert nicht.", "alert-error")
        return redirect(request.args.get("next") or url_for("index"))
    user = current_user()
    if not protocoltype.has_private_view_right(user):
        flash("Dir fehlen die nötigen Zugriffsrechte.", "alert-error")
        return redirect(request.args.get("next") or url_for("index"))
    form = ProtocolTypeForm(obj=protocoltype)
    if form.validate_on_submit():
        if form.private_group.data not in user.groups:
            flash("Du kannst keinen internen Protokolltypen anlegen, zu dem du selbst keinen Zugang hast.", "alert-error")
        else:
            form.populate_obj(protocoltype)
            db.session.commit()
            return redirect(request.args.get("next") or url_for("show_type", type_id=protocoltype.id))
    return render_template("type-edit.html", form=form, protocoltype=protocoltype)

@app.route("/type/show/<int:type_id>")
@login_required
def show_type(type_id):
    protocoltype = ProtocolType.query.filter_by(id=type_id).first()
    if protocoltype is None:
        flash("Dieser Protokolltyp existiert nicht.", "alert-error")
        return redirect(request.args.get("next") or url_for("index"))
    user = current_user()
    if not protocoltype.has_private_view_right(user):
        flash("Dir fehlen die nötigen Zugriffsrechte.", "alert-error")
        return redirect(request.args.get("next") or url_for("index"))
    protocoltype_table = ProtocolTypeTable(protocoltype)
    default_tops_table = DefaultTOPsTable(protocoltype.default_tops, protocoltype)
    reminders_table = MeetingRemindersTable(protocoltype.reminders, protocoltype)
    return render_template("type-show.html", protocoltype=protocoltype, protocoltype_table=protocoltype_table, default_tops_table=default_tops_table, reminders_table=reminders_table)

@app.route("/type/reminders/new/<int:type_id>", methods=["GET", "POST"])
@login_required
def new_reminder(type_id):
    protocoltype = ProtocolType.query.filter_by(id=type_id).first()
    if protocoltype is None:
        flash("Dieser Protokolltyp existiert nicht.", "alert-error")
        return redirect(request.args.get("next") or url_for("index"))
    user = current_user()
    if not protocoltype.has_modify_right(user):
        flash("Dir fehlen die nötigen Zugriffsrechte.", "alert-error")
        return redirect(request.args.get("next") or url_for("index"))
    form = MeetingReminderForm()
    if form.validate_on_submit():
        reminder = MeetingReminder(protocoltype.id, form.days_before.data, form.send_public.data, form.send_private.data)
        db.session.add(reminder)
        db.session.commit()
        return redirect(request.args.get("next") or url_for("show_type", type_id=protocoltype.id))
    return render_template("reminder-new.html", form=form, protocoltype=protocoltype)

@app.route("/type/reminder/edit/<int:type_id>/<int:reminder_id>", methods=["GET", "POST"])
@login_required
def edit_reminder(type_id, reminder_id):
    protocoltype = ProtocolType.query.filter_by(id=type_id).first()
    if protocoltype is None:
        flash("Dieser Protokolltyp existiert nicht.", "alert-error")
        return redirect(request.args.get("next") or url_for("index"))
    user = current_user()
    if not protocoltype.has_modify_right(user):
        flash("Dir fehlen die nötigen Zugriffsrechte.", "alert-error")
        return redirect(request.args.get("next") or url_for("index"))
    reminder = MeetingReminder.query.filter_by(id=reminder_id).first()
    if reminder is None or reminder.protocoltype != protocoltype:
        flash("Invalide Erinnerung.", "alert-error")
        return redirect(request.args.get("next") or url_for("index"))
    form = MeetingReminderForm(obj=reminder)
    if form.validate_on_submit():
        form.populate_obj(reminder)
        db.session.commit()
        return redirect(request.args.get("next") or url_for("show_type", type_id=protocoltype.id))
    return render_template("reminder-edit.html", form=form, protocoltype=protocoltype, reminder=reminder)

@app.route("/type/reminder/delete/<int:type_id>/<int:reminder_id>")
@login_required
def delete_reminder(type_id, reminder_id):
    protocoltype = ProtocolType.query.filter_by(id=type_id).first()
    if protocoltype is None:
        flash("Dieser Protokolltyp existiert nicht.", "alert-error")
        return redirect(request.args.get("next") or url_for("index"))
    user = current_user()
    if not protocoltype.has_modify_right(user):
        flash("Dir fehlen die nötigen Zugriffsrechte.", "alert-error")
        return redirect(request.args.get("next") or url_for("index"))
    reminder = MeetingReminder.query.filter_by(id=reminder_id).first()
    if reminder is None or reminder.protocoltype != protocoltype:
        flash("Invalide Erinnerung.", "alert-error")
        return redirect(request.args.get("next") or url_for("index"))
    db.session.delete(reminder)
    db.session.commit()
    return redirect(request.args.get("next") or url_for("show_type", type_id=protocoltype.id))


@app.route("/type/tops/new/<int:type_id>", methods=["GET", "POST"])
@login_required
def new_default_top(type_id):
    protocoltype = ProtocolType.query.filter_by(id=type_id).first()
    if protocoltype is None:
        flash("Dieser Protokolltyp existiert nicht.", "alert-error")
        return redirect(request.args.get("next") or url_for("index"))
    user = current_user()
    if not protocoltype.has_modify_right(user):
        flash("Dir fehlen die nötigen Zugriffsrechte.", "alert-error")
        return redirect(request.args.get("next") or url_for("index"))
    form = DefaultTopForm()
    if form.validate_on_submit():
        default_top = DefaultTOP(protocoltype.id, form.name.data, form.number.data)
        db.session.add(default_top)
        db.session.commit()
        flash("Der Standard-TOP {} wurde für dem Protokolltyp {} hinzugefügt.".format(default_top.name, protocoltype.name), "alert-success")
        return redirect(request.args.get("next") or url_for("index"))
    return render_template("default-top-new.html", form=form, protocoltype=protocoltype)

@app.route("/type/tops/edit/<int:type_id>/<int:top_id>", methods=["GET", "POST"])
@login_required
def edit_default_top(type_id, top_id):
    protocoltype = ProtocolType.query.filter_by(id=type_id).first()
    if protocoltype is None:
        flash("Dieser Protokolltyp existiert nicht.", "alert-error")
        return redirect(request.args.get("next") or url_for("index"))
    user = current_user()
    if not protocoltype.has_modify_right(user):
        flash("Dir fehlen die nötigen Zugriffsrechte.", "alert-error")
        return redirect(request.args.get("next") or url_for("index"))
    default_top = DefaultTOP.query.filter_by(id=top_id).first()
    if default_top is None or default_top.protocoltype != protocoltype:
        flash("Invalider Standard-TOP.", "alert-error")
        return redirect(request.args.get("next") or url_for("index"))
    form = DefaultTopForm(obj=default_top)
    if form.validate_on_submit():
        form.populate_obj(default_top)
        db.session.commit()
        return redirect(request.args.get("next") or url_for("show_type", type_id=protocoltype.id))
    return render_template("default-top-edit.html", form=form, protocoltype=protocoltype, default_top=default_top)

@app.route("/type/tops/delete/<int:type_id>/<int:top_id>")
@login_required
def delete_default_top(type_id, top_id):
    protocoltype = ProtocolType.query.filter_by(id=type_id).first()
    if protocoltype is None:
        flash("Dieser Protokolltyp existiert nicht.", "alert-error")
        return redirect(request.args.get("next") or url_for("index"))
    user = current_user()
    if not protocoltype.has_modify_right(user):
        flash("Dir fehlen die nötigen Zugriffsrechte.", "alert-error")
        return redirect(request.args.get("next") or url_for("index"))
    default_top = DefaultTOP.query.filter_by(id=top_id).first()
    if default_top is None or default_top.protocoltype != protocoltype:
        flash("Invalider Standard-TOP.", "alert-error")
        return redirect(request.args.get("nexT") or url_for("index"))
    db.session.delete(default_top)
    db.session.commit()
    return redirect(request.args.get("next") or url_for("show_type", type_id=protocoltype.id))

@app.route("/type/tops/move/<int:type_id>/<int:top_id>/<diff>/")
@login_required
def move_default_top(type_id, top_id, diff):
    protocoltype = ProtocolType.query.filter_by(id=type_id).first()
    if protocoltype is None:
        flash("Dieser Protokolltyp existiert nicht.", "alert-error")
        return redirect(request.args.get("next") or url_for("index"))
    user = current_user()
    if not protocoltype.has_modify_right(user):
        flash("Dir fehlen die nötigen Zugriffsrechte.", "alert-error")
        return redirect(request.args.get("next") or url_for("index"))
    default_top = DefaultTOP.query.filter_by(id=top_id).first()
    if default_top is None or default_top.protocoltype != protocoltype:
        flash("Invalider Standard-TOP.", "alert-error")
        return redirect(request.args.get("next") or url_for("index"))
    default_top.number += int(diff)
    db.session.commit()
    return redirect(request.args.get("next") or url_for("show_type", type_id=protocoltype.id))


@app.route("/protocols/list")
def list_protocols():
    is_logged_in = check_login()
    user = current_user()
    protocols = [
        protocol for protocol in Protocol.query.all()
        if (not is_logged_in and protocol.protocoltype.is_public)
        or (is_logged_in and (
            protocol.protocoltype.public_group in user.groups
            or protocol.protocoltype.private_group in user.groups))]
    # TODO: sort by date and paginate
    protocols_table = ProtocolsTable(protocols)
    return render_template("protocols-list.html", protocols=protocols, protocols_table=protocols_table)

@app.route("/protocol/new", methods=["GET", "POST"])
@login_required
def new_protocol():
    user = current_user()
    protocoltypes = ProtocolType.query.all()
    form = NewProtocolForm(protocoltypes)
    if form.validate_on_submit():
        protocoltype = ProtocolType.query.filter_by(id=form.protocoltype.data).first()
        if protocoltype is None or not protocoltype.has_modify_right(user):
            flash("Dir fehlen die nötigen Zugriffsrechte.", "alert-error")
            return redirect(request.args.get("next") or url_for("index"))
        protocol = Protocol(protocoltype.id, form.date.data)
        db.session.add(protocol)
        db.session.commit()
        return redirect(request.args.get("next") or url_for("list_protocols"))
    return render_template("protocol-new.html", form=form, protocoltypes=protocoltypes)

@app.route("/protocol/show/<int:protocol_id>")
def show_protocol(protocol_id):
    user = current_user()
    protocol = Protocol.query.filter_by(id=protocol_id).first()
    if protocol is None or not protocol.protocoltype.has_public_view_right(user):
        flash("Invalides Protokoll.", "alert-error")
        return redirect(request.args.get("next") or url_for("index"))
    errors_table = ErrorsTable(protocol.errors)
    documents_table = DocumentsTable(protocol.documents)
    document_upload_form = DocumentUploadForm()
    return render_template("protocol-show.html", protocol=protocol, errors_table=errors_table, documents_table=documents_table, document_upload_form=document_upload_form)

@app.route("/protocol/etherpull/<int:protocol_id>")
def etherpull_protocol(protocol_id):
    user = current_user()
    protocol = Protocol.query.filter_by(id=protocol_id).first()
    if protocol is None or not protocol.protocoltype.has_modify_right(user):
        flash("Invalides Protokoll oder keine Berechtigung.", "alert-error")
        return redirect(request.args.get("next") or url_for("index"))
    source_req = requests.get(protocol.get_etherpad_source_link())
    source = source_req.text
    protocol.source = source
    db.session.commit()
    tasks.parse_protocol(protocol)
    flash("Das Protokoll wird kompiliert.", "alert-success")
    return redirect(request.args.get("next") or url_for("show_protocol", protocol_id=protocol.id))

@app.route("/protocol/source/<int:protocol_id>")
@login_required
def get_protocol_source(protocol_id):
    user = current_user()
    protocol = Protocol.query.filter_by(id=protocol_id).first()
    if protocol is None or not protocol.protocoltype.has_modify_right(user):
        flash("Invalides Protokoll oder keine Berechtigung.", "alert-error")
        return redirect(request.args.get("next") or url_for("index"))
    file_like = BytesIO(protocol.source.encode("utf-8"))
    return send_file(file_like, cache_timeout=1, as_attachment=True, attachment_filename="{}.txt".format(protocol.get_identifier()))

@app.route("/protocol/update/<int:protocol_id>")
@login_required
def update_protocol(protocol_id):
    user = current_user()
    protocol = Protocol.query.filter_by(id=protocol_id).first()
    if protocol is None or not protocol.protocoltype.has_modify_right(user):
        flash("Invalides Protokoll oder keine Berechtigung.", "alert-error")
        return redirect(request.args.get("next") or url_for("index"))
    # TODO: render form to upload a new version


@app.route("/todos/list")
def list_todos():
    is_logged_in = check_login()
    user = current_user()
    todos = Todos.query.all()
    # TODO: paginate
    todos_table = TodosTable(todos)
    return render_template("todos-list.html", todos=todos, todos_table=todos_table)

@app.route("/document/download/<int:document_id>")
def download_document(document_id):
    user = current_user()
    document = Document.query.filter_by(id=document_id).first()
    if document is None:
        flash("Invalides Dokument.", "alert-error")
        return redirect(request.args.get("next") or url_for("index"))
    if ((document.is_private
            and not document.protocol.protocoltype.has_private_view_right(user))
        or (not document.is_private
            and not document.protocol.protocoltype.has_public_view_right(user))):
        flash("Keine Berechtigung.", "alert-error")
        return redirect(request.args.get("next") or url_for("index"))
    with open(document.get_filename(), "rb") as file:
        file_like = BytesIO(file.read())
        return send_file(file_like, cache_timeout=1, as_attachment=True, attachment_filename=document.name)

@app.route("/document/upload/<int:protocol_id>", methods=["POST"])
@login_required
def upload_document(protocol_id):
    user = current_user()
    protocol = Protocol.query.filter_by(id=protocol_id).first()
    if protocol is None or not protocol.protocoltype.has_modify_right(user):
        flash("Insufficient permissions.", "alert-error")
        return redirect(request.args.get("next") or url_for("index"))
    form = DocumentUploadForm()
    print(form, form.document.data, form.private.data)
    print(request.files)
    if form.document.data is None:
        flash("No file has been selected.", "alert-error")
        return redirect(request.args.get("next") or url_for("index"))
    file = form.document.data
    if file.filename == "":
        flash("No file has been selected.", "alert-error")
        return redirect(request.args.get("next") or url_for("index"))
    if file:
        filename = secure_filename(file.filename)
        internal_filename = "{}-{}".format(protocol.id, filename)
        file.save(os.path.join(config.DOCUMENTS_PATH, internal_filename))
        document = Document(protocol.id, filename, internal_filename, False, form.private.data)
        db.session.add(document)
        db.session.commit()
    return redirect(request.args.get("next") or url_for("show_protocol", protocol_id=protocol.id))


@app.route("/login", methods=["GET", "POST"])
def login():
    if "auth" in session:
        flash("You are already logged in.", "alert-success")
        return redirect(request.args.get("next") or url_for("index"))
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
