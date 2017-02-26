#!/usr/bin/env python3
import locale
locale.setlocale(locale.LC_TIME, "de_DE.utf8")

from flask import Flask, g, current_app, request, session, flash, redirect, url_for, abort, render_template, Response, send_file
from werkzeug.utils import secure_filename
from flask_script import Manager, prompt
from flask_migrate import Migrate, MigrateCommand
#from flask_socketio import SocketIO
from celery import Celery
from sqlalchemy import or_, and_
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
import atexit
from io import StringIO, BytesIO
import os
from datetime import datetime
import math

import config
from shared import db, date_filter, datetime_filter, date_filter_long, time_filter, ldap_manager, security_manager, current_user, check_login, login_required, group_required, class_filter
from utils import is_past, mail_manager, url_manager, get_first_unused_int, set_etherpad_text, get_etherpad_text, split_terms, optional_int_arg
from models.database import ProtocolType, Protocol, DefaultTOP, TOP, Document, Todo, Decision, MeetingReminder, Error
from views.forms import LoginForm, ProtocolTypeForm, DefaultTopForm, MeetingReminderForm, NewProtocolForm, DocumentUploadForm, KnownProtocolSourceUploadForm, NewProtocolSourceUploadForm, ProtocolForm, TopForm, SearchForm, NewProtocolFileUploadForm, NewTodoForm, TodoForm
from views.tables import ProtocolsTable, ProtocolTypesTable, ProtocolTypeTable, DefaultTOPsTable, MeetingRemindersTable, ErrorsTable, TodosTable, DocumentsTable, DecisionsTable, TodoTable, ErrorTable

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

def make_scheduler(app, config, function):
    scheduler = BackgroundScheduler()
    scheduler.start()
    scheduler.add_job(
        func=function,
        trigger=CronTrigger(hour='*'),
        id="scheduler",
        name="Do an action regularly",
        replace_existing=True)
    atexit.register(scheduler.shutdown)

app.jinja_env.trim_blocks = True
app.jinja_env.lstrip_blocks = True
app.jinja_env.filters["datify"] = date_filter
app.jinja_env.filters["datetimify"] = datetime_filter
app.jinja_env.filters["timify"] = time_filter
app.jinja_env.filters["datify_long"] = date_filter_long
app.jinja_env.filters["url_complete"] = url_manager.complete
app.jinja_env.filters["class"] = class_filter
app.jinja_env.tests["auth_valid"] = security_manager.check_user

import tasks

app.jinja_env.globals.update(check_login=check_login)
app.jinja_env.globals.update(current_user=current_user)
app.jinja_env.globals.update(zip=zip)
app.jinja_env.globals.update(min=min)
app.jinja_env.globals.update(max=max)
app.jinja_env.globals.update(dir=dir)

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
                form.organization.data, form.usual_time.data, form.is_public.data,
                form.private_group.data, form.public_group.data,
                form.private_mail.data, form.public_mail.data,
                form.use_wiki.data, form.wiki_category.data,
                form.wiki_only_public.data, form.printer.data)
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
        reminder = MeetingReminder(protocoltype.id, form.days_before.data, form.send_public.data, form.send_private.data, form.additional_text.data)
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
    try:
        default_top.number += int(diff)
        db.session.commit()
    except ValueError:
        flash("Die angegebene Differenz ist keine Zahl.", "alert-error")
    return redirect(request.args.get("next") or url_for("show_type", type_id=protocoltype.id))


@app.route("/protocols/list")
def list_protocols():
    is_logged_in = check_login()
    user = current_user()
    protocoltype = None
    protocoltype_id = None
    try:
        protocoltype_id = int(request.args.get("protocoltype"))
    except (ValueError, TypeError):
        pass
    search_term = request.args.get("search")
    protocoltypes = ProtocolType.get_public_protocoltypes(user)
    search_form = SearchForm(protocoltypes)
    if protocoltype_id is not None:
        search_form.protocoltype.data = protocoltype_id
        protocoltype = ProtocolType.query.filter_by(id=protocoltype_id).first()
    if search_term is not None:
        search_form.search.data = search_term
    protocol_query = Protocol.query
    shall_search = search_term is not None and len(search_term.strip()) > 0
    search_terms = []
    if shall_search:
        search_terms = list(map(str.lower, split_terms(search_term)))
        for term in search_terms:
            protocol_query = protocol_query.filter(or_(
                Protocol.content_public.ilike("%{}%".format(term)),
                Protocol.content_private.ilike("%{}%".format(term))
            ))
    protocols = [
        protocol for protocol in protocol_query.all()
        if (not is_logged_in and protocol.protocoltype.is_public)
        or (is_logged_in and (
            protocol.protocoltype.public_group in user.groups
            or protocol.protocoltype.private_group in user.groups))]
    def _matches_search(content):
        content = content.lower()
        for search_term in search_terms:
            if search_term.lower() not in content:
                return False
        return True
    def _matches_search_lazy(content):
        content = content.lower()
        for search_term in search_terms:
            if search_term.lower() in content:
                return True
        return False
    search_results = {} if shall_search else None
    if protocoltype_id is not None and protocoltype_id != -1:
        protocols = [
            protocol for protocol in protocols
            if protocol.protocoltype.id == protocoltype_id
        ]
    if shall_search:
        protocols = [
            protocol for protocol in protocols
            if (protocol.protocoltype.has_private_view_right(user)
                and _matches_search(protocol.content_private))
            or (protocol.protocoltype.has_public_view_right(user)
                and _matches_search(protocol.content_public))
        ]
        for protocol in protocols:
            content = protocol.content_private if protocol.protocoltype.has_private_view_right(user) else protocol.content_public
            lines = content.splitlines()
            matches = [line for line in lines if _matches_search_lazy(line)]
            formatted_lines = []
            for line in matches:
                parts = []
                lower_line = line.lower()
                last_index = 0
                while last_index < len(line):
                    index_candidates = list(filter(lambda t: t[0] != -1, 
                        [(lower_line.find(term, last_index), term) for term in search_terms]))
                    if len(index_candidates) == 0:
                        parts.append((line[last_index:], False))
                        break
                    else:
                        new_index, term = min(index_candidates, key=lambda t: t[0])
                        new_end_index = new_index + len(term)
                        parts.append((line[last_index:new_index], False))
                        parts.append((line[new_index:new_end_index], True))
                        last_index = new_end_index
                formatted_lines.append("".join([
                    "<b>{}</b>".format(text) if matched else text
                    for text, matched in parts
                ]))
            search_results[protocol] = "<br />\n".join(formatted_lines)
    protocols = sorted(protocols, key=lambda protocol: protocol.date, reverse=True)
    page = _get_page()
    page_count = int(math.ceil(len(protocols)) / config.PAGE_LENGTH)
    if page >= page_count:
        page = 0
    begin_index = page * config.PAGE_LENGTH
    end_index = (page + 1) * config.PAGE_LENGTH
    protocols = protocols[begin_index:end_index]
    protocols_table = ProtocolsTable(protocols, search_results=search_results)
    return render_template("protocols-list.html", protocols=protocols, protocols_table=protocols_table, search_form=search_form, page=page, page_count=page_count, page_diff=config.PAGE_DIFF, protocoltype_id=protocoltype_id, search_term=search_term)

@app.route("/protocol/new", methods=["GET", "POST"])
@login_required
def new_protocol():
    user = current_user()
    protocoltypes = ProtocolType.get_modifiable_protocoltypes(user)
    form = NewProtocolForm(protocoltypes)
    upload_form = NewProtocolSourceUploadForm(protocoltypes)
    file_upload_form = NewProtocolFileUploadForm(protocoltypes)
    if form.validate_on_submit():
        protocoltype = ProtocolType.query.filter_by(id=form.protocoltype.data).first()
        if protocoltype is None or not protocoltype.has_modify_right(user):
            flash("Dir fehlen die nötigen Zugriffsrechte.", "alert-error")
            return redirect(request.args.get("next") or url_for("index"))
        protocol = Protocol(protocoltype.id, form.date.data)
        db.session.add(protocol)
        db.session.commit()
        return redirect(request.args.get("next") or url_for("show_protocol", protocol_id=protocol.id))
    type_id = request.args.get("type_id")
    if type_id is not None:
        form.protocoltype.data = type_id
        upload_form.protocoltype.data = type_id
    return render_template("protocol-new.html", form=form, upload_form=upload_form, file_upload_form=file_upload_form, protocoltypes=protocoltypes)

@app.route("/protocol/show/<int:protocol_id>")
def show_protocol(protocol_id):
    user = current_user()
    protocol = Protocol.query.filter_by(id=protocol_id).first()
    if protocol is None or not protocol.protocoltype.has_public_view_right(user):
        flash("Invalides Protokoll.", "alert-error")
        return redirect(request.args.get("next") or url_for("index"))
    errors_table = ErrorsTable(protocol.errors)
    visible_documents = [
        document for document in protocol.documents
        if (not document.is_private and document.protocol.protocoltype.has_public_view_right(user))
        or (document.is_private and document.protocol.protocoltype.has_private_view_right(user))
    ]
    documents_table = DocumentsTable(visible_documents)
    document_upload_form = DocumentUploadForm()
    source_upload_form = KnownProtocolSourceUploadForm()
    return render_template("protocol-show.html", protocol=protocol, errors_table=errors_table, documents_table=documents_table, document_upload_form=document_upload_form, source_upload_form=source_upload_form)

@app.route("/protocol/delete/<int:protocol_id>")
@login_required
def delete_protocol(protocol_id):
    user = current_user()
    protocol = Protocol.query.filter_by(id=protocol_id).first()
    if protocol is None or not protocol.protocoltype.has_modify_right(user):
        flash("Invalides Protokoll oder keine Berechtigung.", "alert-error")
        return redirect(request.args.get("next") or url_for("index"))
    name = protocol.get_identifier()
    protocol.delete_orphan_todos()
    db.session.delete(protocol)
    db.session.commit()
    flash("Protokoll {} ist gelöscht.".format(name), "alert-success")
    return redirect(request.args.get("next") or url_for("list_protocols"))

@app.route("/protocol/etherpull/<int:protocol_id>")
@login_required
def etherpull_protocol(protocol_id):
    user = current_user()
    protocol = Protocol.query.filter_by(id=protocol_id).first()
    if protocol is None or not protocol.protocoltype.has_modify_right(user):
        flash("Invalides Protokoll oder keine Berechtigung.", "alert-error")
        return redirect(request.args.get("next") or url_for("index"))
    protocol.source = get_etherpad_text(protocol.get_identifier())
    db.session.commit()
    tasks.parse_protocol(protocol)
    flash("Das Protokoll wird kompiliert.", "alert-success")
    return redirect(request.args.get("next") or url_for("show_protocol", protocol_id=protocol.id))

@app.route("/protocol/upload/known/<int:protocol_id>", methods=["POST"])
@login_required
def upload_source_to_known_protocol(protocol_id):
    user = current_user()
    protocol = Protocol.query.filter_by(id=protocol_id).first()
    if protocol is None or not protocol.protocoltype.has_modify_right(user):
        flash("Invalides Protokoll oder keine Berechtigung.", "alert-error")
        return redirect(request.args.get("next") or url_for("index"))
    form = KnownProtocolSourceUploadForm()
    if form.validate_on_submit():
        if form.source.data is None:
            flash("Es wurde keine Datei ausgewählt.", "alert-error")
        else:
            file = form.source.data
            if file.filename == "":
                flash("Es wurde keine Datei ausgewählt.", "alert-error")
            else:
                # todo: Prüfen, ob es Text ist?
                source = file.stream.read().decode("utf-8")
                protocol.source = source
                db.session.commit()
                tasks.parse_protocol(protocol)
                flash("Das Protokoll wird kompiliert.", "alert-success")
    return redirect(request.args.get("next") or url_for("show_protocol", protocol_id=protocol.id))

@app.route("/protocol/upload/new/", methods=["POST"])
@login_required
def upload_new_protocol():
    user = current_user()
    available_types = ProtocolType.get_modifiable_protocoltypes()
    form = NewProtocolSourceUploadForm(protocoltypes=available_types)
    if form.validate_on_submit():
        if form.source.data is None:
            flash("Es wurde keine Datei ausgewählt.", "alert-error")
            return redirect(request.args.get("fail") or url_for("new_protocol"))
        file = form.source.data
        if file.filename == "":
            flash("Es wurde keine Datei ausgewählt.", "alert-error")
            return redirect(request.args.get("fail") or url_for("new_protocol"))
        source = file.stream.read().decode("utf-8")
        protocoltype = ProtocolType.query.filter_by(id=form.protocoltype.data).first()
        if protocoltype is None or not protocoltype.has_modify_right(user):
            flash("Invalider Protokolltyp oder keine Rechte.", "alert-error")
            return redirect(request.args.get("fail") or url_for("new_protocol"))
        protocol = Protocol(protocoltype.id, None, source)
        db.session.add(protocol)
        db.session.commit()
        tasks.parse_protocol(protocol)
        return redirect(request.args.get("next") or url_for("show_protocol", protocol_id=protocol.id))
    return redirect(request.args.get("fail") or url_for("new_protocol"))

@app.route("/protocol/upload/new/file/", methods=["POST"])
@login_required
def upload_new_protocol_by_file():
    user = current_user()
    available_types = ProtocolType.get_modifiable_protocoltypes(user)
    form = NewProtocolFileUploadForm(protocoltypes=available_types)
    if form.validate_on_submit():
        if form.file.data is None:
            flash("Es wurde keine Datei ausgewählt.", "alert-error")
            return redirect(request.args.get("fail") or url_for("new_protocol"))
        file = form.file.data
        if file.filename == "":
            flash("Es wurde keine Datei ausgewählt.", "alert-error")
            return redirect(request.args.get("fail") or url_for("new_protocol"))
        filename = secure_filename(file.filename)
        protocoltype = ProtocolType.query.filter_by(id=form.protocoltype.data).first()
        if protocoltype is None or not protocoltype.has_modify_right(user):
            flash("Invalider Protokolltyp oder keine Rechte.", "alert-error")
            return redirect(request.args.get("fail") or url_for("new_protocol"))
        protocol = Protocol(protocoltype.id, datetime.now().date(), done=True)
        db.session.add(protocol)
        db.session.commit()
        document = Document(protocol.id, filename, "", False, form.private.data)
        db.session.add(document)
        db.session.commit()
        internal_filename = "{}-{}-{}".format(protocol.id, document.id, filename)
        document.filename = internal_filename
        file.save(os.path.join(config.DOCUMENTS_PATH, internal_filename))
        db.session.commit()
        return redirect(request.args.get("next") or url_for("show_protocol", protocol_id=protocol.id))
    return redirect(request.args.get("fail") or url_for("new_protocol"))



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

@app.route("/protocol/template/<int:protocol_id>")
@login_required
def get_protocol_template(protocol_id):
    user = current_user()
    protocol = Protocol.query.filter_by(id=protocol_id).first()
    if protocol is None or not protocol.protocoltype.has_modify_right(user):
        flash("Invalides Protokoll oder keine Berechtigung.", "alert-error")
        return redirect(request.args.get("next") or url_for("index"))
    file_like = BytesIO(protocol.get_template().encode("utf-8"))
    return send_file(file_like, cache_timeout=1, as_attachment=True, attachment_filename="{}-template.txt".format(protocol.get_identifier()))

@app.route("/protocol/etherpush/<int:protocol_id>")
@login_required
def etherpush_protocol(protocol_id):
    user = current_user()
    protocol = Protocol.query.filter_by(id=protocol_id).first()
    if protocol is None or not protocol.protocoltype.has_modify_right(user):
        flash("Invalides Protokoll oder keine Berechtigung.", "alert-error")
        return redirect(request.args.get("next") or url_for("index"))
    if set_etherpad_text(protocol.get_identifier(), protocol.get_template()):
        flash("Vorlage von {} in Etherpad hochgeladen.".format(protocol.get_identifier()), "alert-success")
    else:
        flash("Das Etherpad wurde bereits bearbeitet.", "alert-error")
    return redirect(request.args.get("next") or url_for("show_protocol", protocol_id=protocol.id))

@app.route("/protocol/update/<int:protocol_id>", methods=["GET", "POST"])
@login_required
def update_protocol(protocol_id):
    user = current_user()
    protocol = Protocol.query.filter_by(id=protocol_id).first()
    if protocol is None or not protocol.protocoltype.has_modify_right(user):
        flash("Invalides Protokoll oder keine Berechtigung.", "alert-error")
        return redirect(request.args.get("next") or url_for("index"))
    upload_form = KnownProtocolSourceUploadForm()
    edit_form = ProtocolForm(obj=protocol)
    if edit_form.validate_on_submit():
        edit_form.populate_obj(protocol)
        db.session.commit()
        return redirect(request.args.get("next") or url_for("show_protocol", protocol_id=protocol.id))
    return render_template("protocol-update.html", upload_form=upload_form, edit_form=edit_form, protocol=protocol)

@app.route("/prococol/send/<int:protocol_id>")
@login_required
def send_protocol(protocol_id):
    user = current_user()
    protocol = Protocol.query.filter_by(id=protocol_id).first()
    if protocol is None or not protocol.protocoltype.has_modify_right(user):
        flash("Invalides Protokoll oder keine Berechtigung.", "alert-error")
        return redirect(request.args.get("next") or url_for("index"))
    tasks.send_protocol(protocol)
    flash("Das Protokoll wurde versandt.", "alert-success")
    return redirect(request.args.get("next") or url_for("show_protocol", protocol_id=protocol.id))
    

@app.route("/protocol/tops/new/<int:protocol_id>", methods=["GET", "POST"])
@login_required
def new_top(protocol_id):
    user = current_user()
    protocol = Protocol.query.filter_by(id=protocol_id).first()
    if protocol is None or not protocol.protocoltype.has_modify_right(user):
        flash("Invalides Protokoll oder keine Berechtigung.", "alert-error")
        return redirect(request.args.get("next") or url_for("index"))
    form = TopForm()
    if form.validate_on_submit():
        top = TOP(protocol_id=protocol.id, name=form.name.data, number=form.number.data, planned=True)
        db.session.add(top)
        db.session.commit()
        return redirect(request.args.get("next") or url_for("show_protocol", protocol_id=protocol.id))
    else:
        print(form.number.data)
        current_numbers = list(map(lambda t: t.number, protocol.tops))
        suggested_number = get_first_unused_int(current_numbers)
        form.number.data = suggested_number
    return render_template("top-new.html", form=form, protocol=protocol)

@app.route("/protocol/top/edit/<int:top_id>", methods=["GET", "POST"])
@login_required
def edit_top(top_id):
    user = current_user()
    top = TOP.query.filter_by(id=top_id).first()
    if top is None or not top.protocol.protocoltype.has_modify_right(user):
        flash("Invalider TOP oder keine Berechtigung.", "alert-error")
        return redirect(request.args.get("next") or url_for("index"))
    form = TopForm(obj=top)
    if form.validate_on_submit():
        form.populate_obj(top)
        db.session.commit()
        return redirect(request.args.get("next") or url_for("show_protocol", protocol_id=top.protocol.id))
    return render_template("top-edit.html", form=form, top=top)

@app.route("/protocol/top/delete/<int:top_id>")
@login_required
def delete_top(top_id):
    user = current_user()
    top = TOP.query.filter_by(id=top_id).first()
    if top is None or not top.protocol.protocoltype.has_modify_right(user):
        flash("Invalider TOP oder keine Berechtigung.", "alert-error")
        return redirect(request.args.get("next") or url_for("index"))
    name = top.name
    protocol_id = top.protocol.id
    db.session.delete(top)
    db.session.commit()
    flash("Der TOP {} wurde gelöscht.".format(name), "alert-success")
    return redirect(request.args.get("next") or url_for("show_protocol", protocol_id=protocol_id))

@app.route("/protocol/top/move/<int:top_id>/<diff>")
@login_required
def move_top(top_id, diff):
    user = current_user()
    top = TOP.query.filter_by(id=top_id).first()
    if top is None or not top.protocol.protocoltype.has_modify_right(user):
        flash("Invalider TOP oder keine Berechtigung.", "alert-error")
        return redirect(request.args.get("next") or url_for("index"))
    try:
        top.number += int(diff)
        db.session.commit()
    except ValueError:
        flash("Die angegebene Differenz ist keine Zahl.", "alert-error")
    return redirect(request.args.get("next") or url_for("show_protocol", protocol_id=top.protocol.id))

def _get_page():
    try:
        page = request.args.get("page")
        if page is None:
            return 0
        return int(page)
    except ValueError:
        return 0

@app.route("/todos/list")
@login_required
def list_todos():
    user = current_user()
    protocoltype = None
    protocoltype_id = None
    try:
        protocoltype_id = int(request.args.get("protocoltype"))
    except (ValueError, TypeError):
        pass
    search_term = request.args.get("search")
    protocoltypes = ProtocolType.get_public_protocoltypes(user)
    search_form = SearchForm(protocoltypes)
    if protocoltype_id is not None:
        search_form.protocoltype.data = protocoltype_id
        protocoltype = ProtocolType.query.filter_by(id=protocoltype_id).first()
    if search_term is not None:
        search_form.search.data = search_term
    todos = [
        todo for todo in Todo.query.all()
        if todo.protocoltype.has_public_view_right(user)
    ]
    if protocoltype_id is not None and protocoltype_id != -1:
        todos = [
            todo for todo in todos
            if todo.protocoltype.id == protocoltype_id
        ]
    if search_term is not None and len(search_term.strip()) > 0:
        todos = [
            todo for todo in todos
            if search_term.lower() in todo.description.lower()
        ]
    def _sort_key(todo):
        first_protocol = todo.get_first_protocol()
        result = (not todo.done, first_protocol.date if first_protocol is not None else datetime.now().date())
        return result
    todos = sorted(todos, key=_sort_key, reverse=True)
    page = _get_page()
    page_count = int(math.ceil(len(todos) / config.PAGE_LENGTH))
    if page >= page_count:
        page = 0
    begin_index = page * config.PAGE_LENGTH
    end_index = (page + 1) * config.PAGE_LENGTH
    todos = todos[begin_index:end_index]
    todos_table = TodosTable(todos)
    return render_template("todos-list.html", todos=todos, todos_table=todos_table, search_form=search_form, page=page, page_count=page_count, page_diff=config.PAGE_DIFF, protocoltype_id=protocoltype_id, search_term=search_term)

@app.route("/todo/new", methods=["GET", "POST"])
@login_required
def new_todo():
    user = current_user()
    protocoltype_id = optional_int_arg("type_id")
    protocol_id = optional_int_arg("protocol_id")
    protocoltype = ProtocolType.query.filter_by(id=protocoltype_id).first()
    protocol = Protocol.query.filter_by(id=protocol_id).first()
    if protocoltype is not None and protocol is not None:
        if protocol.protocoltype != protocoltype:
            flash("Ungültige Protokoll-Typ-Kombination", "alert-error")
            return redirect(request.args.get("next") or url_for("index"))
    if protocoltype is None and protocol is not None:
        protocoltype = protocol.protocoltype
    protocoltypes = ProtocolType.get_modifiable_protocoltypes(user)
    form = NewTodoForm(protocoltypes)
    if form.validate_on_submit():
        added_protocoltype = ProtocolType.query.filter_by(id=form.protocoltype_id.data).first()
        if added_protocoltype is None or not added_protocoltype.has_modify_right(user):
            flash("Invalider Protokolltyp.")
            return redirect(request.args.get("next") or url_for("index"))
        todo = Todo(type_id=form.protocoltype_id.data, who=form.who.data,
            description=form.description.data, tags=form.tags.data,
            done=form.done.data)
        if protocol is not None:
            todo.protocols.append(protocol)
        db.session.add(todo)
        db.session.commit()
        todo.number = todo.id
        db.session.commit()
        flash("Todo wurde angelegt.", "alert-success")
        if protocol is not None:
            return redirect(request.args.get("next") or url_for("show_protocol", protocol_id=protocol.id))
        else:
            return redirect(request.args.get("next") or url_for("list_todos", protocoltype_id=protocoltype_id))
    else:
        if protocoltype is not None:
            form.protocoltype_id.data = protocoltype.id
    return render_template("todo-new.html", form=form, protocol=protocol, protocoltype=protocoltype)

@app.route("/todo/edit/<int:todo_id>", methods=["GET", "POST"])
@login_required
def edit_todo(todo_id):
    user = current_user()
    todo = Todo.query.filter_by(id=todo_id).first()
    if todo is None or not todo.protocoltype.has_modify_right(user):
        flash("Invalides Todo oder unzureichende Berechtigung.", "alert-error")
        return redirect(request.args.get("next") or url_for("index"))
    form = TodoForm(obj=todo)
    if form.validate_on_submit():
        form.populate_obj(todo)
        db.session.commit()
        return redirect(request.args.get("next") or url_for("list_todos", protocoltype=todo.protocoltype.id))
    return render_template("todo-edit.html", form=form, todo=todo)

@app.route("/todo/show/<int:todo_id>")
@login_required
def show_todo(todo_id):
    user = current_user()
    todo = Todo.query.filter_by(id=todo_id).first()
    if todo is None or not todo.protocoltype.has_private_view_right(user):
        flash("Invalides Todo oder unzureichende Berechtigung.", "alert-error")
        return redirect(request.args.get("next") or url_for("index"))
    todo_table = TodoTable(todo)
    return render_template("todo-show.html", todo=todo, todo_table=todo_table)

@app.route("/todo/delete/<int:todo_id>")
@login_required
def delete_todo(todo_id):
    user = current_user()
    todo = Todo.query.filter_by(id=todo_id).first()
    if todo is None or not todo.protocoltype.has_private_view_right(user):
        flash("Invalides Todo oder unzureichende Berechtigung.", "alert-error")
        return redirect(request.args.get("next") or url_for("index"))
    type_id = todo.protocoltype.id
    db.session.delete(todo)
    db.session.commit()
    flash("Todo gelöscht.", "alert-success")
    return redirect(request.args.get("next") or url_for("list_todos", protocoltype=type_id))
    


@app.route("/decisions/list")
def list_decisions():
    is_logged_In = check_login()
    user = current_user()
    protocoltype = None
    protocoltype_id = None
    try:
        protocoltype_id = int(request.args.get("protocoltype"))
    except (ValueError, TypeError):
        pass
    search_term = request.args.get("search")
    protocoltypes = ProtocolType.get_public_protocoltypes(user)
    search_form = SearchForm(protocoltypes)
    if protocoltype_id is not None:
        search_form.protocoltype.data = protocoltype_id
        protocoltype = ProtocolType.query.filter_by(id=protocoltype_id).first()
    if search_term is not None:
        search_form.search.data = search_term
    decisions = [
        decision for decision in Decision.query.all()
        if decision.protocol.protocoltype.has_public_view_right(user)
    ]
    if protocoltype_id is not None and protocoltype_id != -1:
        decisions = [
            decision for decision in decisions 
            if decision.protocol.protocoltype.id == protocoltype_id
        ]
    if search_term is not None and len(search_term.strip()) > 0:
        decisions = [
            decision for decision in decisions
            if search_term.lower() in decision.content.lower()
        ]
    page = _get_page()
    page_count = int(math.ceil(len(decisions) / config.PAGE_LENGTH))
    if page >= page_count:
        page = 0
    begin_index = page * config.PAGE_LENGTH
    end_index = (page + 1) * config.PAGE_LENGTH
    decisions = decisions[begin_index:end_index]
    decisions_table = DecisionsTable(decisions)
    return render_template("decisions-list.html", decisions=decisions, decisions_table=decisions_table, search_form=search_form, page=page, page_count=page_count, page_diff=config.PAGE_DIFF, protocoltype_id=protocoltype_id, search_term=search_term)


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
    return send_file(document.as_file_like(), cache_timeout=1, as_attachment=True, attachment_filename=document.name)

@app.route("/document/upload/<int:protocol_id>", methods=["POST"])
@login_required
def upload_document(protocol_id):
    user = current_user()
    protocol = Protocol.query.filter_by(id=protocol_id).first()
    if protocol is None or not protocol.protocoltype.has_modify_right(user):
        flash("Unzureichende Berechtigung.", "alert-error")
        return redirect(request.args.get("next") or url_for("index"))
    form = DocumentUploadForm()
    if form.document.data is None:
        flash("Es wurde keine Datei ausgewählt.", "alert-error")
        return redirect(request.args.get("next") or url_for("index"))
    file = form.document.data
    if file.filename == "":
        flash("Es wurde keine Datei ausgewählt.", "alert-error")
        return redirect(request.args.get("next") or url_for("index"))
    # todo: Dateitypen einschränken?
    if file:
        filename = secure_filename(file.filename)
        document = Document(protocol.id, filename, "", False, form.private.data)
        db.session.add(document)
        db.session.commit()
        internal_filename = "{}-{}-{}".format(protocol.id, document.id, filename)
        document.filename = internal_filename
        file.save(os.path.join(config.DOCUMENTS_PATH, internal_filename))
        if datetime.now().date() >= protocol.date:
            protocol.done = True
        db.session.commit()
    return redirect(request.args.get("next") or url_for("show_protocol", protocol_id=protocol.id))

@app.route("/document/delete/<int:document_id>")
@login_required
def delete_document(document_id):
    user = current_user()
    document = Document.query.filter_by(id=document_id).first()
    if document is None or not document.protocol.protocoltype.has_modify_right(user):
        flash("Unzureichende Berechtigung.", "alert-error")
        return redirect(request.args.get("next") or url_for("index"))
    name = document.name
    protocol = document.protocol
    db.session.delete(document)
    db.session.commit()
    flash("Das Dokument {} wurde gelöscht.".format(name), "alert-success")
    return redirect(request.args.get("next") or url_for("show_protocol", protocol_id=protocol.id))

@app.route("/document/print/<int:document_id>")
@login_required
def print_document(document_id):
    user = current_user()
    document = Document.query.filter_by(id=document_id).first()
    if document is None or not document.protocol.protocoltype.has_modify_right(user):
        flash("Invalides Protokoll oder keine Berechtigung.", "alert-error")
        return redirect(request.args.get("next") or url_for("index"))
    tasks.print_file(document.get_filename(), document.protocol)
    flash("Das Dokument {} wird gedruckt.".format(document.name), "alert-success")
    return redirect(request.args.get("next") or url_for("show_protocol", protocol_id=document.protocol.id))

@app.route("/errors/list")
@login_required
def list_errors():
    user = current_user()
    errors = [
        error for error in Error.query.all()
        if error.protocol.protocoltype.has_private_view_right(user)
    ]
    errors_table = ErrorsTable(errors)
    return render_template("errors-list.html", errros=errors, errors_table=errors_table)

@app.route("/error/show/<int:error_id>")
@login_required
def show_error(error_id):
    user = current_user()
    error = Error.query.filter_by(id=error_id).first()
    if error is None or not error.protocol.protocoltype.has_modify_right(user):
        flash("Invalider Fehler oder fehlende Zugriffsrechte.", "alert-error")
        return redirect(request.args.get("next") or url_for("index"))
    error_table = ErrorTable(error)
    return render_template("error-show.html", error=error, error_table=error_table)

@app.route("/error/delete/<int:error_id>")
@login_required
def delete_error(error_id):
    user = current_user()
    error = Error.query.filter_by(id=error_id).first()
    if error is None or not error.protocol.protocoltype.has_modify_right(user):
        flash("Invalider Fehler oder fehlende Zugriffsrechte.", "alert-error")
        return redirect(request.args.get("next") or url_for("index"))
    name = error.name
    db.session.delete(error)
    db.session.commit()
    flash("Fehler {} gelöscht.".format(name), "alert-success")
    return redirect(request.args.get("next") or url_for("list_errors"))
    

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

def check_and_send_reminders():
    with app.app_context():
        current_time = datetime.now()
        current_day = current_time.date()
        for protocol in Protocol.query.filter(Protocol.done == False).all():
            day_difference = (protocol.date - current_day).days
            usual_time = protocol.protocoltype.usual_time
            protocol_time = datetime(1, 1, 1, usual_time.hour, usual_time.minute)
            hour_difference = (protocol_time - current_time).seconds // 3600
            print(protocol.get_identifier(), day_difference, hour_difference)
            for reminder in protocol.protocoltype.reminders:
                if day_difference == reminder.days_before and hour_difference == 0:
                    tasks.send_reminder(reminder, protocol)

if __name__ == "__main__":
    make_scheduler(app, config, check_and_send_reminders)
    manager.run()
