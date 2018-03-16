#!/usr/bin/env python3
import locale
locale.setlocale(locale.LC_TIME, "de_DE.utf8")

from flask import (
    Flask, request, session, flash, redirect,
    url_for, abort, render_template, Response, Markup)
from werkzeug.utils import secure_filename
from flask_script import Manager, prompt
from flask_migrate import Migrate, MigrateCommand
from celery import Celery
from sqlalchemy import or_
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
import atexit
import feedgen.feed
import icalendar
from io import BytesIO
import os
from datetime import datetime, timedelta
import math
import mimetypes

import config
from shared import (
    db, date_filter, datetime_filter, date_filter_long,
    date_filter_short, time_filter, time_filter_short, user_manager,
    security_manager, current_user, check_login, login_required,
    class_filter, needs_date_test, todostate_name_filter,
    code_filter, code_key_filter, indent_tab_filter)
from utils import (
    get_first_unused_int, get_etherpad_text, split_terms, optional_int_arg,
    fancy_join, footnote_hash, get_git_revision, get_max_page_length_exp,
    get_internal_filename, get_csrf_token)
from decorators import (
    db_lookup, protect_csrf,
    require_private_view_right, require_modify_right, require_publish_right,
    require_admin_right)
from models.database import (
    ProtocolType, Protocol, DefaultTOP, TOP, LocalTOP,
    Document, Todo, Decision, MeetingReminder, Error, TodoMail,
    DecisionDocument, TodoState, DefaultMeta, DecisionCategory, Like)
from views.forms import (
    LoginForm, ProtocolTypeForm, DefaultTopForm,
    MeetingReminderForm, NewProtocolForm, DocumentUploadForm,
    KnownProtocolSourceUploadForm, NewProtocolSourceUploadForm,
    generate_protocol_form, TopForm, LocalTopForm,
    DecisionSearchForm, ProtocolSearchForm, TodoSearchForm,
    NewProtocolFileUploadForm, NewTodoForm, TodoForm, TodoMailForm,
    DefaultMetaForm, MergeTodosForm, DecisionCategoryForm,
    DocumentEditForm)
from views.tables import (
    ProtocolsTable, ProtocolTypesTable,
    ProtocolTypeTable, DefaultTOPsTable, MeetingRemindersTable, ErrorsTable,
    TodosTable, DocumentsTable, DecisionsTable, TodoTable, ErrorTable,
    TodoMailsTable, DefaultMetasTable, DecisionCategoriesTable)
from legacy import import_old_todos, import_old_protocols, import_old_todomails
import back

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

app.jinja_env.trim_blocks = True
app.jinja_env.lstrip_blocks = True
app.jinja_env.filters["datify"] = date_filter
app.jinja_env.filters["datetimify"] = datetime_filter
app.jinja_env.filters["timify"] = time_filter
app.jinja_env.filters["timify_short"] = time_filter_short
app.jinja_env.filters["datify_short"] = date_filter_short
app.jinja_env.filters["datify_long"] = date_filter_long
app.jinja_env.filters["class"] = class_filter
app.jinja_env.filters["todo_get_name"] = todostate_name_filter
app.jinja_env.filters["code"] = code_filter
app.jinja_env.filters["code_key"] = code_key_filter
app.jinja_env.filters["indent_tab"] = indent_tab_filter
app.jinja_env.filters["fancy_join"] = fancy_join
app.jinja_env.filters["footnote_hash"] = footnote_hash
app.jinja_env.tests["auth_valid"] = security_manager.check_user
app.jinja_env.tests["needs_date"] = needs_date_test
app.jinja_env.globals["get_csrf_token"] = get_csrf_token

additional_templates = getattr(config, "LATEX_LOCAL_TEMPLATES", None)
if additional_templates is not None and os.path.isdir(additional_templates):
    if additional_templates not in app.jinja_loader.searchpath:
        app.jinja_loader.searchpath.append(additional_templates)


import tasks

app.jinja_env.globals.update(check_login=check_login)
app.jinja_env.globals.update(current_user=current_user)
app.jinja_env.globals.update(zip=zip)
app.jinja_env.globals.update(min=min)
app.jinja_env.globals.update(max=max)
app.jinja_env.globals.update(dir=dir)
app.jinja_env.globals.update(now=datetime.now)
app.jinja_env.globals["git_revision"] = get_git_revision()


@manager.command
def import_legacy():
    """Import the old todos and protocols from an sql dump"""
    filename = prompt("SQL-file")
    with open(filename, "rb") as sqlfile:
        content = sqlfile.read().decode("utf-8")
        import_old_todos(content)
        import_old_protocols(content)
        import_old_todomails(content)


@manager.command
def recompile_all():
    for protocol in sorted(Protocol.query.all(), key=lambda p: p.date):
        if protocol.is_done():
            print(protocol.get_short_identifier())
            tasks.parse_protocol(protocol)


@manager.command
def merge_duplicate_todos():
    todo_by_id = {}
    todos = Todo.query.all()
    for todo in todos:
        todo_id = todo.get_id()
        if todo_id in todo_by_id:
            todo1, todo2 = todo, todo_by_id[todo_id]
            print(todo1)
            print(todo2)
            if todo2.state.value > todo1.state.value:
                todo2, todo1 = todo1, todo2
            for protocol in todo2.protocols:
                if protocol not in todo1.protocols:
                    todo1.protocols.append(protocol)
                todo2.protocols.remove(protocol)
            db.session.delete(todo2)
            db.session.commit()
            todo_by_id[todo_id] = todo1
        else:
            todo_by_id[todo_id] = todo


@manager.command
def runserver():
    app.run()
    make_scheduler()


def send_file(file_like, cache_timeout, as_attachment, attachment_filename):
    """
    Replaces flask.send_file since that uses an uwsgi function that is buggy.
    """
    mimetype, _ = mimetypes.guess_type(attachment_filename)
    response = Response(file_like.read(), mimetype)
    if as_attachment:
        response.headers["Content-Disposition"] = (
            'attachment; filename="{}"'.format(attachment_filename))
    content_type = mimetype
    if mimetype.startswith("text/"):
        content_type = "{}; charset=utf-8".format(content_type)
    response.headers["Content-Type"] = content_type
    response.headers["Cache-Control"] = (
        "public, max-age={}".format(cache_timeout))
    response.headers["Connection"] = "close"
    return response


@app.route("/")
@back.anchor
def index():
    user = current_user()
    protocols = [
        protocol for protocol in Protocol.query.all()
        if protocol.protocoltype.has_public_view_right(
            user, check_networks=False)
    ]

    def _protocol_sort_key(protocol):
        if protocol.date is not None:
            return protocol.date
        return datetime.now().date()
    current_day = datetime.now().date()
    open_protocols = sorted(
        [
            protocol for protocol in protocols
            if not protocol.done
            and (protocol.date - current_day).days < config.MAX_INDEX_DAYS
            and (current_day - protocol.date).days < config.MAX_PAST_INDEX_DAYS
        ],
        key=_protocol_sort_key
    )
    finished_protocols = sorted(
        [
            protocol for protocol in protocols
            if protocol.done and protocol.public
            and (
                protocol.has_private_view_right(user)
                or protocol.protocoltype.has_public_view_right(
                    user, check_networks=False))
        ],
        key=_protocol_sort_key,
        reverse=True
    )
    protocol = None
    show_private = False
    has_public_view_right = False
    if len(finished_protocols) > 0:
        protocol = finished_protocols[0]
        show_private = protocol.has_private_view_right(user)
        has_public_view_right = (
            protocol.protocoltype.has_public_view_right(user))
    todos = None
    if check_login():
        todos = [
            todo for todo in Todo.query.all()
            if todo.protocoltype.has_private_view_right(user)
            and not todo.is_done()
        ]
        user_todos = [
            todo for todo in todos
            if user.username.lower()
            in list(map(str.strip, todo.who.lower().split(",")))
        ]
        if len(user_todos) > 0:
            todos = user_todos

        def _todo_sort_key(todo):
            protocol = todo.get_first_protocol()
            if protocol is not None and protocol.date is not None:
                return protocol.date
            return datetime.now().date()
        todos = sorted(todos, key=_todo_sort_key, reverse=True)
    return render_template(
        "index.html", open_protocols=open_protocols,
        protocol=protocol, todos=todos, show_private=show_private,
        has_public_view_right=has_public_view_right)

@app.route("/documentation")
@back.anchor
@login_required
def documentation():
    return render_template(
        "documentation.html")

@app.route("/documentation/sessionmanagement")
@back.anchor
@login_required
def sessionmanagement_documentation():
    return render_template(
        "documentation-sessionmanagement.html")

@app.route("/documentation/sessionmanagement/plan")
@back.anchor
@login_required
def plan_sessionmanagement_documentation():
    return render_template(
        "documentation-sessionmanagement-plan.html")

@app.route("/documentation/sessionmanagement/write")
@back.anchor
@login_required
def write_sessionmanagement_documentation():
    return render_template(
        "documentation-sessionmanagement-write.html")

@app.route("/documentation/sessionmanagement/tracking")
@back.anchor
@login_required
def tracking_sessionmanagement_documentation():
    return render_template(
        "documentation-sessionmanagement-tracking.html")

@app.route("/documentation/syntax")
@back.anchor
@login_required
def syntax_documentation():
    return render_template(
        "documentation-syntax.html")

@app.route("/documentation/syntax/meta")
@back.anchor
@login_required
def meta_syntax_documentation():
    return render_template(
        "documentation-syntax-meta.html")

@app.route("/documentation/syntax/top")
@back.anchor
@login_required
def top_syntax_documentation():
    return render_template(
        "documentation-syntax-top.html")

@app.route("/documentation/syntax/lists")
@back.anchor
@login_required
def lists_syntax_documentation():
    return render_template("documentation-syntax-lists.html")

@app.route("/documentation/syntax/internal")
@back.anchor
@login_required
def internal_syntax_documentation():
    return render_template(
        "documentation-syntax-internal.html")

@app.route("/documentation/syntax/tags")
@back.anchor
@login_required
def tags_syntax_documentation():
    todostates = list(TodoState)
    name_to_state = TodoState.get_name_to_state()
    return render_template(
        "documentation-syntax-tags.html", todostates=todostates,
        name_to_state=name_to_state)

@app.route("/documentation/configuration")
@back.anchor
@login_required
def configuration_documentation():
    return render_template(
        "documentation-configuration.html")

@app.route("/documentation/configuration/types")
@back.anchor
@login_required
def types_configuration_documentation():
    return render_template(
        "documentation-configuration-types.html")

@app.route("/documentation/configuration/todomails")
@back.anchor
@login_required
def todomails_configuration_documentation():
    return render_template(
        "documentation-configuration-todomails.html")

@app.route("/documentation/configuration/settings")
@back.anchor
@login_required
def settings_configuration_documentation():
    return render_template(
        "documentation-configuration-settings.html")

@app.route("/types/list")
@back.anchor
@login_required
def list_types():
    user = current_user()
    types = [
        protocoltype for protocoltype in ProtocolType.query.all()
        if (protocoltype.has_private_view_right(user)
            or protocoltype.has_public_view_right(user)
            or protocoltype.is_public)]
    types = sorted(types, key=lambda t: t.short_name)
    types_table = ProtocolTypesTable(types)
    return render_template(
        "types-list.html", types=types, types_table=types_table)


@app.route("/type/new", methods=["GET", "POST"])
@login_required
def new_type():
    form = ProtocolTypeForm()
    if form.validate_on_submit():
        user = current_user()
        if form.private_group.data not in user.groups:
            flash("Du kannst keinen internen Protokolltypen anlegen, "
                  "zu dem du selbst keinen Zugang hast.", "alert-error")
        else:
            protocoltype = ProtocolType()
            form.populate_obj(protocoltype)
            db.session.add(protocoltype)
            db.session.commit()
            flash("Der Protokolltyp {} wurde angelegt.".format(
                protocoltype.name), "alert-success")
        return back.redirect("list_types")
    return render_template("type-new.html", form=form)


@app.route("/type/edit/<int:protocoltype_id>", methods=["GET", "POST"])
@login_required
@db_lookup(ProtocolType)
@require_private_view_right()
def edit_type(protocoltype):
    user = current_user()
    form = ProtocolTypeForm(obj=protocoltype)
    if form.validate_on_submit():
        if form.private_group.data not in user.groups:
            flash("Du kannst keinen internen Protokolltypen anlegen, "
                  "zu dem du selbst keinen Zugang hast.", "alert-error")
        else:
            form.populate_obj(protocoltype)
            db.session.commit()
            return back.redirect("show_type", protocoltype_id=protocoltype.id)
    return render_template(
        "type-edit.html", form=form, protocoltype=protocoltype)


@app.route("/type/show/<int:protocoltype_id>")
@back.anchor
@login_required
@db_lookup(ProtocolType)
@require_private_view_right()
def show_type(protocoltype):
    protocoltype_table = ProtocolTypeTable(protocoltype)
    default_tops_table = DefaultTOPsTable(
        protocoltype.default_tops, protocoltype)
    reminders_table = MeetingRemindersTable(
        protocoltype.reminders, protocoltype)
    metas_table = DefaultMetasTable(protocoltype.metas, protocoltype)
    categories_table = DecisionCategoriesTable(
        protocoltype.decisioncategories, protocoltype)
    return render_template(
        "type-show.html", protocoltype=protocoltype,
        protocoltype_table=protocoltype_table,
        default_tops_table=default_tops_table, metas_table=metas_table,
        reminders_table=reminders_table, mail_active=config.MAIL_ACTIVE,
        categories_table=categories_table)


@app.route("/type/delete/<int:protocoltype_id>")
@login_required
@protect_csrf
@db_lookup(ProtocolType)
@require_admin_right()
@require_modify_right()
def delete_type(protocoltype):
    name = protocoltype.name
    db.session.delete(protocoltype)
    db.session.commit()
    flash("Der Protokolltype {} wurde gelöscht.".format(name), "alert-success")
    return back.redirect("list_types")


@app.route("/type/reminders/new/<int:protocoltype_id>",
           methods=["GET", "POST"])
@login_required
@db_lookup(ProtocolType)
@require_modify_right()
def new_reminder(protocoltype):
    form = MeetingReminderForm()
    if form.validate_on_submit():
        meetingreminder = MeetingReminder(protocoltype_id=protocoltype.id)
        form.populate_obj(meetingreminder)
        db.session.add(meetingreminder)
        db.session.commit()
        return back.redirect("show_type", protocoltype_id=protocoltype.id)
    return render_template(
        "reminder-new.html", form=form, protocoltype=protocoltype)


@app.route("/type/reminder/edit/<int:meetingreminder_id>",
           methods=["GET", "POST"])
@login_required
@db_lookup(MeetingReminder)
@require_modify_right()
def edit_reminder(meetingreminder):
    form = MeetingReminderForm(obj=meetingreminder)
    if form.validate_on_submit():
        form.populate_obj(meetingreminder)
        db.session.commit()
        return back.redirect(
            "show_type", protocoltype_id=meetingreminder.protocoltype.id)
    return render_template(
        "reminder-edit.html", form=form, meetingreminder=meetingreminder)


@app.route("/type/reminder/delete/<int:meetingreminder_id>")
@login_required
@protect_csrf
@db_lookup(MeetingReminder)
@require_modify_right()
def delete_reminder(meetingreminder):
    protocoltype = meetingreminder.protocoltype
    db.session.delete(meetingreminder)
    db.session.commit()
    return back.redirect("show_type", protocoltype_id=protocoltype.id)


@app.route("/type/tops/new/<int:protocoltype_id>", methods=["GET", "POST"])
@login_required
@db_lookup(ProtocolType)
@require_modify_right()
def new_default_top(protocoltype):
    form = DefaultTopForm()
    if form.validate_on_submit():
        defaulttop = DefaultTOP(protocoltype_id=protocoltype.id)
        form.populate_obj(defaulttop)
        db.session.add(defaulttop)
        db.session.commit()
        for protocol in protocoltype.protocols:
            if not protocol.done:
                localtop = LocalTOP(
                    protocol_id=protocol.id,
                    defaulttop_id=defaulttop.id, description="")
                db.session.add(localtop)
        db.session.commit()
        flash("Der Standard-TOP {} wurde für dem Protokolltyp {} hinzugefügt."
              .format(defaulttop.name, protocoltype.name), "alert-success")
        return back.redirect()
    return render_template(
        "default-top-new.html", form=form, protocoltype=protocoltype)


@app.route("/type/tops/edit/<int:protocoltype_id>/<int:defaulttop_id>",
           methods=["GET", "POST"])
@login_required
@db_lookup(ProtocolType, DefaultTOP)
@require_modify_right()
def edit_default_top(protocoltype, defaulttop):
    form = DefaultTopForm(obj=defaulttop)
    if form.validate_on_submit():
        form.populate_obj(defaulttop)
        db.session.commit()
        return back.redirect("show_type", protocoltype_id=protocoltype.id)
    return render_template(
        "default-top-edit.html", form=form,
        protocoltype=protocoltype, defaulttop=defaulttop)


@app.route("/type/tops/delete/<int:defaulttop_id>")
@login_required
@protect_csrf
@db_lookup(DefaultTOP)
@require_modify_right()
def delete_default_top(defaulttop):
    db.session.delete(defaulttop)
    db.session.commit()
    return back.redirect(
        "show_type", protocoltype_id=defaulttop.protocoltype.id)


@app.route("/type/tops/move/<int:defaulttop_id>/<diff>/")
@login_required
@protect_csrf
@db_lookup(DefaultTOP)
@require_modify_right()
def move_default_top(defaulttop, diff):
    try:
        defaulttop.number += int(diff)
        db.session.commit()
    except ValueError:
        flash("Die angegebene Differenz ist keine Zahl.", "alert-error")
    return back.redirect(
        "show_type", protocoltype_id=defaulttop.protocoltype.id)


@app.route("/protocols/list")
@back.anchor
def list_protocols():
    user = current_user()
    protocoltype_id = None
    try:
        protocoltype_id = int(request.args.get("protocoltype_id"))
    except (ValueError, TypeError):
        pass
    state_open = -1
    try:
        state_open = int(request.args.get("state_open"))
    except (ValueError, TypeError):
        pass
    search_term = request.args.get("search")
    protocoltypes = ProtocolType.get_public_protocoltypes(
        user, check_networks=False)
    search_form = ProtocolSearchForm(protocoltypes)
    if protocoltype_id is not None:
        search_form.protocoltype_id.data = protocoltype_id
    if state_open is not None:
        search_form.state_open.data = state_open
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
        if protocol.protocoltype.has_public_view_right(
            user, check_networks=False)
    ]

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
    if state_open is not None and state_open != -1:
        protocol_done = bool(state_open)
        protocols = [
            protocol for protocol in protocols
            if (protocol.is_done() or False) == protocol_done
        ]
    if shall_search:
        protocols = [
            protocol for protocol in protocols
            if (protocol.protocoltype.has_private_view_right(user)
                and _matches_search(protocol.content_private))
            or (protocol.has_public_view_right(user)
                and _matches_search(protocol.content_public))
        ]
        for protocol in protocols:
            content = protocol.get_visible_content(user)
            lines = content.splitlines()
            matches = [line for line in lines if _matches_search_lazy(line)]
            formatted_lines = []
            for line in matches:
                parts = []
                lower_line = line.lower()
                last_index = 0
                while last_index < len(line):
                    index_candidates = list(filter(
                        lambda t: t[0] != -1,
                        [
                            (lower_line.find(term, last_index), term)
                            for term in search_terms
                        ]))
                    if len(index_candidates) == 0:
                        parts.append((line[last_index:], False))
                        break
                    else:
                        new_index, term = min(
                            index_candidates, key=lambda t: t[0])
                        new_end_index = new_index + len(term)
                        parts.append((line[last_index:new_index], False))
                        parts.append((line[new_index:new_end_index], True))
                        last_index = new_end_index
                formatted_lines.append("".join([
                    "<b>{}</b>".format(text) if matched else text
                    for text, matched in parts
                ]))
            search_results[protocol] = " …<br />\n".join(formatted_lines)
    protocols = sorted(
        protocols, key=lambda protocol: protocol.date, reverse=True)
    page = _get_page()
    page_length = _get_page_length()
    page_count = int(math.ceil(len(protocols) / page_length))
    if page >= page_count:
        page = 0
    begin_index = page * page_length
    end_index = (page + 1) * page_length
    max_page_length_exp = get_max_page_length_exp(protocols)
    protocols = protocols[begin_index:end_index]
    protocols_table = ProtocolsTable(protocols, search_results=search_results)
    return render_template(
        "protocols-list.html", protocols=protocols,
        protocols_table=protocols_table, search_form=search_form, page=page,
        page_count=page_count, page_diff=config.PAGE_DIFF,
        protocoltype_id=protocoltype_id, search_term=search_term,
        state_open=state_open, page_length=page_length,
        max_page_length_exp=max_page_length_exp)


@app.route("/protocol/new", methods=["GET", "POST"])
@login_required
def new_protocol():
    user = current_user()
    protocoltypes = ProtocolType.get_modifiable_protocoltypes(user)
    form = NewProtocolForm(protocoltypes)
    upload_form = NewProtocolSourceUploadForm(protocoltypes)
    file_upload_form = NewProtocolFileUploadForm(protocoltypes)
    if form.validate_on_submit():
        protocoltype = ProtocolType.query.filter_by(
            id=form.protocoltype_id.data).first()
        if protocoltype is None or not protocoltype.has_modify_right(user):
            flash("Dir fehlen die nötigen Zugriffsrechte.", "alert-error")
            return back.redirect()
        protocol = Protocol.create_new_protocol(
            protocoltype, form.date.data, form.start_time.data)
        return back.redirect("show_protocol", protocol_id=protocol.id)
    type_id = request.args.get("protocoltype_id")
    if type_id is not None:
        form.protocoltype.data = type_id
        upload_form.protocoltype.data = type_id
    return render_template(
        "protocol-new.html", form=form,
        upload_form=upload_form, file_upload_form=file_upload_form,
        protocoltypes=protocoltypes)


@app.route("/protocol/show/<int:protocol_id>")
@back.anchor
@db_lookup(Protocol)
def show_protocol(protocol):
    user = current_user()
    errors_table = ErrorsTable(protocol.errors)
    if not protocol.protocoltype.has_public_view_right(
            user, check_networks=False):
        flash("Dir fehlen die nötigen Zugriffsrechte.", "alert-error")
        if check_login():
            return redirect(url_for("index"))
        return redirect(url_for("login"))
    visible_documents = [
        document for document in protocol.documents
        if (not document.is_private
            and document.protocol.has_public_view_right(user))
        or (document.is_private
            and document.protocol.protocoltype.has_private_view_right(user))
    ]
    documents_table = DocumentsTable(visible_documents, protocol)
    document_upload_form = DocumentUploadForm()
    source_upload_form = KnownProtocolSourceUploadForm()
    time_diff = protocol.date - datetime.now().date()
    large_time_diff = not protocol.is_done() and time_diff.days > 0
    content_html = (
        protocol.content_html_private
        if protocol.has_private_view_right(user)
        else protocol.content_html_public)
    if content_html is not None:
        content_html = Markup(content_html)
    return render_template(
        "protocol-show.html", protocol=protocol,
        errors_table=errors_table, documents_table=documents_table,
        document_upload_form=document_upload_form,
        source_upload_form=source_upload_form, time_diff=time_diff,
        large_time_diff=large_time_diff, content_html=content_html)


@app.route("/protocol/delete/<int:protocol_id>")
@login_required
@protect_csrf
@db_lookup(Protocol)
@require_admin_right()
@require_modify_right()
def delete_protocol(protocol):
    name = protocol.get_short_identifier()
    protocol.delete_orphan_todos()
    db.session.delete(protocol)
    db.session.commit()
    flash("Protokoll {} ist gelöscht.".format(name), "alert-success")
    return back.redirect("list_protocols")


@app.route("/protocol/etherpull/<int:protocol_id>")
@login_required
@protect_csrf
@db_lookup(Protocol)
@require_modify_right()
def etherpull_protocol(protocol):
    if not config.ETHERPAD_ACTIVE:
        flash("Die Etherpadfunktion ist nicht aktiviert.", "alert-error")
        return back.redirect("show_protocol", protocol_id=protocol.id)
    protocol.source = get_etherpad_text(protocol.get_identifier())
    db.session.commit()
    tasks.parse_protocol(protocol)
    flash("Das Protokoll wird kompiliert.", "alert-success")
    return back.redirect("show_protocol", protocol_id=protocol.id)


@app.route("/protocol/upload/known/<int:protocol_id>", methods=["POST"])
@login_required
@db_lookup(Protocol)
@require_modify_right()
def upload_source_to_known_protocol(protocol):
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
    return back.redirect("show_protocol", protocol_id=protocol.id)


@app.route("/protocol/upload/new/", methods=["POST"])
@login_required
def upload_new_protocol():
    user = current_user()
    available_types = ProtocolType.get_modifiable_protocoltypes(user)
    form = NewProtocolSourceUploadForm(protocoltypes=available_types)
    if form.validate_on_submit():
        if form.source.data is None:
            flash("Es wurde keine Datei ausgewählt.", "alert-error")
            return redirect(request.args.get("fail")
                            or url_for("new_protocol"))
        file = form.source.data
        if file.filename == "":
            flash("Es wurde keine Datei ausgewählt.", "alert-error")
            return redirect(request.args.get("fail")
                            or url_for("new_protocol"))
        source = file.stream.read().decode("utf-8")
        protocoltype = ProtocolType.query.filter_by(
            id=form.protocoltype_id.data).first()
        if protocoltype is None or not protocoltype.has_modify_right(user):
            flash("Invalider Protokolltyp oder keine Rechte.", "alert-error")
            return redirect(request.args.get("fail")
                            or url_for("new_protocol"))
        protocol = Protocol(protocoltype_id=protocoltype.id, source=source)
        db.session.add(protocol)
        db.session.commit()
        for local_top in protocol.create_localtops():
            db.session.add(local_top)
        db.session.commit()
        tasks.parse_protocol(protocol)
        return back.redirect("show_protocol", protocol_id=protocol.id)
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
            return redirect(request.args.get("fail")
                            or url_for("new_protocol"))
        file = form.file.data
        if file.filename == "":
            flash("Es wurde keine Datei ausgewählt.", "alert-error")
            return redirect(request.args.get("fail")
                            or url_for("new_protocol"))
        filename = secure_filename(file.filename)
        protocoltype = ProtocolType.query.filter_by(
            id=form.protocoltype_id.data).first()
        if protocoltype is None or not protocoltype.has_modify_right(user):
            flash("Invalider Protokolltyp oder keine Rechte.", "alert-error")
            return redirect(request.args.get("fail")
                            or url_for("new_protocol"))
        protocol = Protocol(
            protocoltype_id=protocoltype.id,
            date=datetime.now().date(), done=True)
        db.session.add(protocol)
        db.session.commit()
        for local_top in protocol.create_localtops():
            db.session.add(local_top)
        db.session.commit()
        document = Document(
            protocol_id=protocol.id, name=filename,
            filename="", is_compiled=False)
        form.populate_obj(document)
        db.session.add(document)
        db.session.commit()
        internal_filename = get_internal_filename(
            protocol, document.id, filename)
        document.filename = internal_filename
        file.save(os.path.join(config.DOCUMENTS_PATH, internal_filename))
        db.session.commit()
        return back.redirect("show_protocol", protocol_id=protocol.id)
    return redirect(request.args.get("fail") or url_for("new_protocol"))


@app.route("/protocol/recompile/<int:protocol_id>")
@login_required
@protect_csrf
@db_lookup(Protocol)
@require_admin_right()
@require_modify_right()
def recompile_protocol(protocol):
    tasks.parse_protocol(protocol)
    return back.redirect("show_protocol", protocol_id=protocol.id)


@app.route("/protocol/source/<int:protocol_id>")
@login_required
@db_lookup(Protocol)
@require_modify_right()
def get_protocol_source(protocol):
    file_like = BytesIO(protocol.source.encode("utf-8"))
    return send_file(
        file_like, cache_timeout=1, as_attachment=True,
        attachment_filename="{}.txt".format(protocol.get_short_identifier()))


@app.route("/protocol/template/<int:protocol_id>")
@login_required
@db_lookup(Protocol)
@require_modify_right()
def get_protocol_template(protocol):
    file_like = BytesIO(protocol.get_template().encode("utf-8"))
    return send_file(
        file_like, cache_timeout=1, as_attachment=True,
        attachment_filename="{}-template.txt".format(
            protocol.get_short_identifier()))


@app.route("/protocol/etherpush/<int:protocol_id>")
@login_required
@protect_csrf
@db_lookup(Protocol)
@require_modify_right()
def etherpush_protocol(protocol):
    if not config.ETHERPAD_ACTIVE:
        flash("Die Etherpadfunktion ist nicht aktiviert.", "alert-error")
        return back.redirect("show_protocol", protocol_id=protocol.id)
    if not protocol.is_done():
        tasks.set_etherpad_content(protocol)
    return redirect(protocol.get_etherpad_link())


@app.route("/protocol/update/<int:protocol_id>", methods=["GET", "POST"])
@login_required
@db_lookup(Protocol)
@require_publish_right()
def update_protocol(protocol):
    upload_form = KnownProtocolSourceUploadForm()
    edit_form = generate_protocol_form(protocol)(obj=protocol)
    if edit_form.validate_on_submit():
        edit_form.populate_obj(protocol)
        for meta in protocol.metas:
            meta.value = getattr(edit_form.metas, meta.name).data
        db.session.commit()
        tasks.push_tops_to_calendar(protocol)
        return back.redirect("show_protocol", protocol_id=protocol.id)
    for meta in protocol.metas:
        getattr(edit_form.metas, meta.name).data = meta.value
    return render_template(
        "protocol-update.html", upload_form=upload_form,
        edit_form=edit_form, protocol=protocol)


@app.route("/protocol/publish/<int:protocol_id>")
@login_required
@protect_csrf
@db_lookup(Protocol)
@require_publish_right()
def publish_protocol(protocol):
    protocol.public = True
    db.session.commit()
    return back.redirect("show_protocol", protocol_id=protocol.id)


@app.route("/prococol/send/private/<int:protocol_id>")
@login_required
@protect_csrf
@db_lookup(Protocol)
@require_modify_right()
def send_protocol_private(protocol):
    if not config.MAIL_ACTIVE:
        flash("Die Mailfunktion ist nicht aktiviert.", "alert-error")
        return back.redirect("show_protocol", protocol_id=protocol.id)
    tasks.send_protocol_private(protocol)
    flash("Das Protokoll wurde versandt.", "alert-success")
    return back.redirect("show_protocol", protocol_id=protocol.id)


@app.route("/prococol/send/public/<int:protocol_id>")
@login_required
@protect_csrf
@db_lookup(Protocol)
@require_publish_right()
def send_protocol_public(protocol):
    if not config.MAIL_ACTIVE:
        flash("Die Mailfunktion ist nicht aktiviert.", "alert-error")
        return back.redirect("show_protocol", protocol_id=protocol.id)
    tasks.send_protocol_public(protocol)
    flash("Das Protokoll wurde versandt.", "alert-success")
    return back.redirect("show_protocol", protocol_id=protocol.id)


@app.route("/protocol/reminder/<int:protocol_id>")
@login_required
@protect_csrf
@db_lookup(Protocol)
@require_modify_right()
def send_protocol_reminder(protocol):
    if not config.MAIL_ACTIVE:
        flash("Die Mailfunktion ist nicht aktiviert.", "alert-error")
        return back.redirect("show_protocol", protocol_id=protocol.id)
    meetingreminders = protocol.reminders
    if len(meetingreminders) == 0:
        flash("Für diesen Protokolltyp sind keine Einladungsmails "
              "konfiguriert.", "alert-error")
        return back.redirect("show_protocol", protocol_id=protocol.id)
    day_difference = (protocol.date - datetime.now().date()).days
    past_reminders = [
        meetingreminder for meetingreminder in meetingreminders
        if meetingreminder.days_before > day_difference
    ]
    if len(past_reminders) == 0:
        flash("Bisher hätte keine Einladungsmail verschickt werden sollen, "
              "schicke letzte.", "alert-info")
        past_reminders = meetingreminders
    past_reminders = sorted(past_reminders, key=lambda r: r.days_before)
    choosen_reminder = past_reminders[0]
    tasks.send_reminder(choosen_reminder, protocol)
    flash("Einladungsmail ist versandt.", "alert-success")
    return back.redirect("show_protocol", protocol_id=protocol.id)


@app.route("/protocol/tops/new/<int:protocol_id>", methods=["GET", "POST"])
@login_required
@db_lookup(Protocol)
@require_modify_right()
def new_top(protocol):
    form = TopForm()
    if form.validate_on_submit():
        top = TOP(protocol_id=protocol.id, planned=True)
        form.populate_obj(top)
        db.session.add(top)
        db.session.commit()
        tasks.push_tops_to_calendar(top.protocol)
        return back.redirect("show_protocol", protocol_id=protocol.id)
    else:
        current_numbers = list(map(lambda t: t.number, protocol.tops))
        suggested_number = get_first_unused_int(current_numbers)
        form.number.data = suggested_number
    return render_template("top-new.html", form=form, protocol=protocol)


@app.route("/protocol/top/edit/<int:top_id>", methods=["GET", "POST"])
@login_required
@db_lookup(TOP)
@require_modify_right()
def edit_top(top):
    form = TopForm(obj=top)
    if form.validate_on_submit():
        form.populate_obj(top)
        db.session.commit()
        tasks.push_tops_to_calendar(top.protocol)
        return back.redirect("show_protocol", protocol_id=top.protocol.id)
    return render_template("top-edit.html", form=form, top=top)


@app.route("/protocol/top/delete/<int:top_id>")
@login_required
@protect_csrf
@db_lookup(TOP)
@require_modify_right()
def delete_top(top):
    name = top.name
    protocol = top.protocol
    db.session.delete(top)
    db.session.commit()
    tasks.push_tops_to_calendar(protocol)
    flash("Der TOP {} wurde gelöscht.".format(name), "alert-success")
    return back.redirect("show_protocol", protocol_id=protocol.id)


@app.route("/protocol/top/move/<int:top_id>/<diff>")
@login_required
@protect_csrf
@db_lookup(TOP)
@require_modify_right()
def move_top(top, diff):
    try:
        top.number += int(diff)
        db.session.commit()
        tasks.push_tops_to_calendar(top.protocol)
    except ValueError:
        flash("Die angegebene Differenz ist keine Zahl.", "alert-error")
    return back.redirect("show_protocol", protocol_id=top.protocol.id)


@app.route("/protocol/localtop/edit/<int:localtop_id>",
           methods=["GET", "POST"])
@login_required
@db_lookup(LocalTOP)
@require_modify_right()
def edit_localtop(localtop):
    form = LocalTopForm(obj=localtop)
    if form.validate_on_submit():
        form.populate_obj(localtop)
        db.session.commit()
        return back.redirect("show_protocol", protocol_id=localtop.protocol.id)
    return render_template("localtop-edit.html", form=form, localtop=localtop)


def _get_page():
    try:
        page = request.args.get("page")
        if page is None:
            return 0
        return int(page)
    except ValueError:
        return 0


def _get_page_length():
    try:
        page_length = request.args.get("page_length")
        if page_length is None:
            return config.PAGE_LENGTH
        return int(page_length)
    except ValueError:
        return config.PAGE_LENGTH


@app.route("/todos/list")
@back.anchor
@login_required
def list_todos():
    user = current_user()
    protocoltype_id = None
    try:
        protocoltype_id = int(request.args.get("protocoltype_id"))
    except (ValueError, TypeError):
        pass
    state_open = -1
    try:
        state_open = int(request.args.get("state_open"))
    except (ValueError, TypeError):
        pass
    search_term = request.args.get("search")
    protocoltypes = ProtocolType.get_public_protocoltypes(user)
    search_form = TodoSearchForm(protocoltypes)
    if protocoltype_id is not None:
        search_form.protocoltype_id.data = protocoltype_id
    if state_open is not None:
        search_form.state_open.data = state_open
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
    if state_open is not None and state_open != -1:
        todo_done = bool(state_open)
        todos = [
            todo for todo in todos
            if todo.is_done() == todo_done
        ]
    if search_term is not None and len(search_term.strip()) > 0:
        todos = [
            todo for todo in todos
            if search_term.lower() in todo.description.lower()
            or search_term.lower() in todo.who.lower()
        ]

    def _sort_key(todo):
        return (not todo.is_done(), todo.get_id())
    todos = sorted(todos, key=_sort_key, reverse=True)
    page = _get_page()
    page_length = _get_page_length()
    page_count = int(math.ceil(len(todos) / page_length))
    if page >= page_count:
        page = 0
    begin_index = page * page_length
    end_index = (page + 1) * page_length
    max_page_length_exp = get_max_page_length_exp(todos)
    todos = todos[begin_index:end_index]
    todos_table = TodosTable(todos)
    return render_template(
        "todos-list.html", todos=todos,
        todos_table=todos_table, search_form=search_form, page=page,
        page_count=page_count, page_diff=config.PAGE_DIFF,
        protocoltype_id=protocoltype_id, search_term=search_term,
        state_open=state_open, page_length=page_length,
        max_page_length_exp=max_page_length_exp)


@app.route("/todo/new", methods=["GET", "POST"])
@login_required
def new_todo():
    user = current_user()
    protocoltype_id = optional_int_arg("protocoltype_id")
    protocol_id = optional_int_arg("protocol_id")
    protocoltype = ProtocolType.query.filter_by(id=protocoltype_id).first()
    protocol = Protocol.query.filter_by(id=protocol_id).first()
    if protocoltype is not None and protocol is not None:
        if protocol.protocoltype != protocoltype:
            flash("Ungültige Protokoll-Typ-Kombination", "alert-error")
            return back.redirect()
    if protocoltype is None and protocol is not None:
        protocoltype = protocol.protocoltype
    protocoltypes = ProtocolType.get_modifiable_protocoltypes(user)
    form = NewTodoForm(protocoltypes)
    if form.validate_on_submit():
        added_protocoltype = ProtocolType.query.filter_by(
            id=form.protocoltype_id.data).first()
        if (added_protocoltype is None
                or not added_protocoltype.has_modify_right(user)):
            flash("Invalider Protokolltyp.")
            return back.redirect()
        todo = Todo()
        form.populate_obj(todo)
        if protocol is not None:
            todo.protocols.append(protocol)
        db.session.add(todo)
        db.session.commit()
        todo.number = todo.id
        db.session.commit()
        flash("Todo wurde angelegt.", "alert-success")
        if protocol is not None:
            return back.redirect("show_protocol", protocol_id=protocol.id)
        else:
            return back.redirect("list_todos", protocoltype_id=protocoltype_id)
    else:
        if protocoltype is not None:
            form.protocoltype_id.data = protocoltype.id
    return render_template(
        "todo-new.html", form=form, protocol=protocol,
        protocoltype=protocoltype)


@app.route("/todo/edit/<int:todo_id>", methods=["GET", "POST"])
@login_required
@db_lookup(Todo)
@require_modify_right()
def edit_todo(todo):
    form = TodoForm(obj=todo)
    if form.validate_on_submit():
        form.populate_obj(todo)
        db.session.commit()
        return back.redirect(
            "list_todos", protocoltype_id=todo.protocoltype.id)
    return render_template("todo-edit.html", form=form, todo=todo)


@app.route("/todo/show/<int:todo_id>")
@back.anchor
@login_required
@db_lookup(Todo)
@require_private_view_right()
def show_todo(todo):
    todo_table = TodoTable(todo)
    return render_template("todo-show.html", todo=todo, todo_table=todo_table)


@app.route("/todo/delete/<int:todo_id>")
@login_required
@protect_csrf
@db_lookup(Todo)
@require_private_view_right()
def delete_todo(todo):
    type_id = todo.protocoltype.id
    db.session.delete(todo)
    db.session.commit()
    flash("Todo gelöscht.", "alert-success")
    return back.redirect("list_todos", protocoltype_id=type_id)


@app.route("/todo/merge", methods=["GET", "POST"])
@login_required
@require_admin_right()
def merge_todos():
    form = MergeTodosForm(request.args.get("todo_id"))
    if form.validate_on_submit():
        todo1 = Todo.query.filter_by(id=form.todo1.data).first()
        todo2 = Todo.query.filter_by(id=form.todo2.data).first()
        if todo1 is None or todo2 is None:
            flash("Missing todos.", "alert-error")
        else:
            id1 = todo1.id
            id2 = todo2.id
            for protocol in todo2.protocols:
                if protocol not in todo1.protocols:
                    todo1.protocols.append(protocol)
                todo2.protocols.remove(protocol)
            db.session.delete(todo2)
            db.session.commit()
            flash("Merged todos {} and {}.".format(id1, id2), "alert-success")
            return back.redirect("list_todos")
    return render_template("todos-merge.html", form=form)


@app.route("/decisions/list")
@back.anchor
def list_decisions():
    user = current_user()
    protocoltype_id = None
    decisioncategory_id = None
    try:
        protocoltype_id = int(request.args.get("protocoltype_id"))
    except (ValueError, TypeError):
        pass
    try:
        decisioncategory_id = int(request.args.get("decisioncategory_id"))
    except (ValueError, TypeError):
        pass
    search_term = request.args.get("search")
    protocoltypes = ProtocolType.get_public_protocoltypes(
        user, check_networks=False)
    decisioncategories = [
        category
        for protocoltype in protocoltypes
        for category in protocoltype.decisioncategories
    ]
    search_form = DecisionSearchForm(protocoltypes, decisioncategories)
    if protocoltype_id is not None:
        search_form.protocoltype_id.data = protocoltype_id
    if decisioncategory_id is not None:
        search_form.decisioncategory_id.data = decisioncategory_id
    if search_term is not None:
        search_form.search.data = search_term
    decisions = [
        decision for decision in Decision.query.all()
        if decision.protocol.has_public_view_right(user)
    ]
    if protocoltype_id is not None and protocoltype_id != -1:
        decisions = [
            decision for decision in decisions
            if decision.protocol.protocoltype.id == protocoltype_id
        ]
    if decisioncategory_id is not None and decisioncategory_id != -1:
        decisions = [
            decision for decision in decisions
            if decisioncategory_id in map(lambda d: d.id, decision.categories)
        ]
    if search_term is not None and len(search_term.strip()) > 0:
        decisions = [
            decision for decision in decisions
            if search_term.lower() in decision.content.lower()
        ]
    decisions = sorted(decisions, key=lambda d: d.protocol.date, reverse=True)

    page = _get_page()
    page_length = _get_page_length()

    page_count = int(math.ceil(len(decisions) / page_length))
    if page >= page_count:
        page = 0
    begin_index = page * page_length
    end_index = (page + 1) * page_length
    max_page_length_exp = get_max_page_length_exp(decisions)
    decisions = decisions[begin_index:end_index]
    decisions_table = DecisionsTable(decisions)
    return render_template(
        "decisions-list.html", decisions=decisions,
        decisions_table=decisions_table, search_form=search_form, page=page,
        page_count=page_count, page_diff=config.PAGE_DIFF,
        protocoltype_id=protocoltype_id, search_term=search_term,
        decisioncategory_id=decisioncategory_id, page_length=page_length,
        max_page_length_exp=max_page_length_exp)


@app.route("/document/download/<int:document_id>")
@db_lookup(Document)
def download_document(document):
    user = current_user()
    if ((document.is_private
            and not document.protocol.protocoltype
            .has_private_view_right(user))
        or (not document.is_private
            and not document.protocol.has_public_view_right(user))):
        flash("Dir fehlen die nötigen Zugriffsrechte.", "alert-error")
        return back.redirect()
    return send_file(
        document.as_file_like(), cache_timeout=1,
        as_attachment=True, attachment_filename=document.name)


@app.route("/document/upload/<int:protocol_id>", methods=["POST"])
@login_required
@db_lookup(Protocol)
@require_modify_right()
def upload_document(protocol):
    form = DocumentUploadForm()
    if form.document.data is None:
        flash("Es wurde keine Datei ausgewählt.", "alert-error")
        return back.redirect()
    file = form.document.data
    if file.filename == "":
        flash("Es wurde keine Datei ausgewählt.", "alert-error")
        return back.redirect()
    if file:
        filename = secure_filename(file.filename)
        document = Document(
            protocol_id=protocol.id, name=filename,
            filename="", is_compiled=False)
        form.populate_obj(document)
        db.session.add(document)
        db.session.commit()
        internal_filename = get_internal_filename(
            protocol, document, filename)
        document.filename = internal_filename
        file.save(os.path.join(config.DOCUMENTS_PATH, internal_filename))
        if datetime.now().date() >= protocol.date:
            protocol.done = True
        db.session.commit()
    return back.redirect("show_protocol", protocol_id=protocol.id)


@app.route("/document/edit/<int:document_id>", methods=["GET", "POST"])
@login_required
@db_lookup(Document)
@require_modify_right()
def edit_document(document):
    form = DocumentEditForm(obj=document)
    if form.validate_on_submit():
        form.populate_obj(document)
        db.session.commit()
        return back.redirect("show_protocol", protocol_id=document.protocol.id)
    return render_template("document-edit.html", document=document, form=form)


@app.route("/document/delete/<int:document_id>")
@login_required
@protect_csrf
@db_lookup(Document)
@require_admin_right()
@require_modify_right()
def delete_document(document):
    name = document.name
    protocol = document.protocol
    db.session.delete(document)
    db.session.commit()
    flash("Das Dokument {} wurde gelöscht.".format(name), "alert-success")
    return back.redirect("show_protocol", protocol_id=protocol.id)


@app.route("/document/print/<int:document_id>")
@login_required
@protect_csrf
@db_lookup(Document)
@require_modify_right()
def print_document(document):
    if not config.PRINTING_ACTIVE:
        flash("Die Druckfunktion ist nicht aktiviert.", "alert-error")
        return back.redirect("show_protocol", protocol_id=document.protocol.id)
    tasks.print_file(document.get_filename(), document.protocol)
    flash("Das Dokument {} wird gedruckt.".format(document.name),
          "alert-success")
    return back.redirect("show_protocol", protocol_id=document.protocol.id)


@app.route("/decision/print/<int:decisiondocument_id>")
@login_required
@protect_csrf
@db_lookup(DecisionDocument)
@require_modify_right()
def print_decision(decisiondocument):
    if not config.PRINTING_ACTIVE:
        flash("Die Druckfunktion ist nicht aktiviert.", "alert-error")
        return back.redirect(
            "show_protocol",
            protocol_id=decisiondocument.decision.protocol.id)
    tasks.print_file(
        decisiondocument.get_filename(),
        decisiondocument.decision.protocol)
    flash("Das Dokument {} wird gedruckt.".format(decisiondocument.name),
          "alert-success")
    return back.redirect(
        "show_protocol", protocol_id=decisiondocument.decision.protocol.id)


@app.route("/errors/list")
@back.anchor
@login_required
def list_errors():
    user = current_user()
    errors = [
        error for error in Error.query.all()
        if error.protocol.protocoltype.has_private_view_right(user)
    ]
    errors_table = ErrorsTable(errors)
    return render_template(
        "errors-list.html", erros=errors, errors_table=errors_table)


@app.route("/error/show/<int:error_id>")
@back.anchor
@login_required
@db_lookup(Error)
@require_modify_right()
def show_error(error):
    error_table = ErrorTable(error)
    return render_template(
        "error-show.html", error=error, error_table=error_table)


@app.route("/error/delete/<int:error_id>")
@login_required
@protect_csrf
@db_lookup(Error)
@require_modify_right()
def delete_error(error):
    name = error.name
    db.session.delete(error)
    db.session.commit()
    flash("Fehler {} gelöscht.".format(name), "alert-success")
    return back.redirect("list_errors")


@app.route("/todomails/list")
@back.anchor
@login_required
def list_todomails():
    todomails = sorted(TodoMail.query.all(), key=lambda tm: tm.name.lower())
    todomails_table = TodoMailsTable(todomails)
    return render_template(
        "todomails-list.html", todomails=todomails,
        todomails_table=todomails_table)


@app.route("/todomail/new", methods=["GET", "POST"])
@login_required
def new_todomail():
    form = TodoMailForm()
    if form.validate_on_submit():
        todomail = TodoMail()
        form.populate_obj(todomail)
        db.session.add(todomail)
        db.session.commit()
        flash("Die Todomailzuordnung für {} wurde angelegt.".format(
            todomail.name), "alert-success")
        return back.redirect("list_todomails")
    return render_template("todomail-new.html", form=form)


@app.route("/todomail/edit/<int:todomail_id>", methods=["GET", "POST"])
@login_required
@db_lookup(TodoMail)
def edit_todomail(todomail):
    form = TodoMailForm(obj=todomail)
    if form.validate_on_submit():
        form.populate_obj(todomail)
        db.session.commit()
        flash("Die Todo-Mail-Zuordnung wurde geändert.", "alert-success")
        return back.redirect("list_todomails")
    return render_template("todomail-edit.html", todomail=todomail, form=form)


@app.route("/todomail/delete/<int:todomail_id>")
@login_required
@protect_csrf
@db_lookup(TodoMail)
def delete_todomail(todomail):
    name = todomail.name
    db.session.delete(todomail)
    db.session.commit()
    flash("Die Todo-Mail-Zuordnung für {} wurde gelöscht.".format(name),
          "alert-success")
    return back.redirect("list_todomails")


@app.route("/defaultmeta/new/<int:protocoltype_id>", methods=["GET", "POST"])
@login_required
@db_lookup(ProtocolType)
@require_modify_right()
def new_defaultmeta(protocoltype):
    form = DefaultMetaForm()
    if form.validate_on_submit():
        meta = DefaultMeta(protocoltype_id=protocoltype.id)
        form.populate_obj(meta)
        db.session.add(meta)
        db.session.commit()
        flash("Metadatenfeld hinzugefügt.", "alert-success")
        return back.redirect("show_type", protocoltype_id=protocoltype.id)
    return render_template(
        "defaultmeta-new.html", form=form, protocoltype=protocoltype)


@app.route("/defaultmeta/edit/<int:defaultmeta_id>", methods=["GET", "POST"])
@login_required
@db_lookup(DefaultMeta)
@require_modify_right()
def edit_defaultmeta(defaultmeta):
    form = DefaultMetaForm(obj=defaultmeta)
    if form.validate_on_submit():
        form.populate_obj(defaultmeta)
        db.session.commit()
        return back.redirect(
            "show_type", protocoltype_id=defaultmeta.protocoltype.id)
    return render_template(
        "defaultmeta-edit.html", form=form, defaultmeta=defaultmeta)


@app.route("/defaultmeta/delete/<int:defaultmeta_id>")
@login_required
@protect_csrf
@db_lookup(DefaultMeta)
@require_admin_right()
@require_modify_right()
def delete_defaultmeta(defaultmeta):
    name = defaultmeta.name
    type_id = defaultmeta.protocoltype.id
    db.session.delete(defaultmeta)
    db.session.commit()
    flash("Metadatenfeld '{}' gelöscht.".format(name), "alert-success")
    return back.redirect("show_type", protocoltype_id=type_id)


@app.route("/decisioncategory/new/<int:protocoltype_id>",
           methods=["GET", "POST"])
@login_required
@db_lookup(ProtocolType)
@require_modify_right()
def new_decisioncategory(protocoltype):
    form = DecisionCategoryForm()
    if form.validate_on_submit():
        category = DecisionCategory(protocoltype_id=protocoltype.id)
        form.populate_obj(category)
        db.session.add(category)
        db.session.commit()
        flash("Beschlusskategorie hinzugefügt.", "alert-success")
        return back.redirect("show_type", protocoltype_id=protocoltype.id)
    return render_template(
        "decisioncategory-new.html", form=form, protocoltype=protocoltype)


@app.route("/decisioncategory/edit/<int:decisioncategory_id>",
           methods=["GET", "POST"])
@login_required
@db_lookup(DecisionCategory)
@require_modify_right()
def edit_decisioncategory(decisioncategory):
    form = DecisionCategoryForm(obj=decisioncategory)
    if form.validate_on_submit():
        form.populate_obj(decisioncategory)
        db.session.commit()
        return back.redirect(
            "show_type", protocoltype_id=decisioncategory.protocoltype.id)
    return render_template(
        "decisioncategory-edit.html", form=form,
        decisioncategory=decisioncategory)


@app.route("/decisioncategory/delete/<int:decisioncategory_id>")
@login_required
@protect_csrf
@db_lookup(DecisionCategory)
@require_admin_right()
@require_modify_right()
def delete_decisioncategory(decisioncategory):
    name = decisioncategory.name
    type_id = decisioncategory.protocoltype.id
    db.session.delete(decisioncategory)
    db.session.commit()
    flash("Beschlusskategorie {} gelöscht.".format(name), "alert-success")
    return back.redirect("show_type", protocoltype_id=type_id)


def create_protocols_feed(protocoltype):
    if not protocoltype.has_public_anonymous_view_right():
        abort(403)
    protocols = [
        protocol for protocol in protocoltype.protocols
        if protocol.is_done()
    ]
    feed = feedgen.feed.FeedGenerator()
    feed.description(protocoltype.name)
    feed.generator(
        "Protokollsystem 3",
        uri="https://git.fsmpi.rwth-aachen.de/protokollsystem/proto3")
    feed.id(url_for(
        "show_type", protocoltype_id=protocoltype.id, _external=True))
    feed.link(href=url_for(
        "list_protocols", protocoltype_id=protocoltype.id,
        state_open=False, _external=True), rel="alternate")
    feed.title(protocoltype.short_name)
    for protocol in protocols:
        entry = feed.add_entry()
        entry.id(url_for(
            "show_protocol", protocol_id=protocol.id, _external=True))
        entry.link(href=url_for(
            "show_protocol", protocol_id=protocol.id,
            _external=True), rel="alternate")
        document = protocol.get_compiled_document(private=False)
        if document is not None:
            entry.link(href=url_for(
                "download_document", document_id=document.id, _external=True),
                rel="enclosure",
                title="Protokoll", type="application/pdf")
        entry.title(protocol.get_title())
        entry.summary(",\n".join(top.name for top in protocol.get_tops()))
        entry.content(protocol.content_public)
        entry.published(protocol.get_timezone_aware_start_date())
    return feed


def create_appointments_feed(protocoltype):
    if not protocoltype.has_public_anonymous_view_right():
        abort(403)
    protocols = [
        protocol for protocol in protocoltype.protocols
        if not protocol.is_done()
    ]
    feed = feedgen.feed.FeedGenerator()
    feed.description(protocoltype.name)
    feed.generator(
        "Protokollsystem 3",
        uri="https://git.fsmpi.rwth-aachen.de/protokollsystem/proto3")
    feed.id(url_for(
        "show_type", protocoltype_id=protocoltype.id, _external=True))
    feed.link(href=url_for(
        "list_protocols", protocoltype_id=protocoltype.id,
        state_open=True, _external=True), rel="alternate")
    feed.title("{}-Termine".format(protocoltype.short_name))
    for protocol in protocols:
        entry = feed.add_entry()
        entry.id(url_for(
            "show_protocol", protocol_id=protocol.id, _external=True))
        entry.link(href=url_for(
            "show_protocol", protocol_id=protocol.id, _external=True),
            rel="alternate")
        entry.title(protocol.get_title())
        entry.summary("\n".join(
            [
                ",\n".join([
                    "Beginn: {}".format(protocol.get_time())
                ] + [
                    "{}: {}".format(meta.name, meta.value)
                    for meta in protocol.metas
                    if not meta.internal
                ]),
                "Tagesordnung:",
                ",\n".join(
                    "TOP {}".format(top.name)
                    for top in protocol.get_tops()
                )
            ]))
    return feed


@app.route("/feed/protocols/rss/<int:protocoltype_id>")
@db_lookup(ProtocolType)
def feed_protocols_rss(protocoltype):
    return Response(
        create_protocols_feed(protocoltype).rss_str(),
        mimetype="application/rss+xml")


@app.route("/feed/protocols/atom/<int:protocoltype_id>")
@db_lookup(ProtocolType)
def feed_protocols_atom(protocoltype):
    return Response(
        create_protocols_feed(protocoltype).atom_str(),
        mimetype="application/atom+xml")


@app.route("/feed/appointments/rss/<int:protocoltype_id>")
@db_lookup(ProtocolType)
def feed_appointments_rss(protocoltype):
    return Response(
        create_appointments_feed(protocoltype).rss_str(),
        mimetype="application/rss+xml")


@app.route("/feed/appointments/atom/<int:protocoltype_id>")
@db_lookup(ProtocolType)
def feed_appointments_atom(protocoltype):
    return Response(
        create_appointments_feed(protocoltype).atom_str(),
        mimetype="application/atom+xml")


@app.route("/feed/appointments/ical/<int:protocoltype_id>")
@db_lookup(ProtocolType)
def feed_appointments_ical(protocoltype):
    if not protocoltype.has_public_anonymous_view_right():
        abort(403)
    protocols = [
        protocol for protocol in protocoltype.protocols
        if not protocol.is_done()
    ]
    calendar = icalendar.Calendar()
    calendar["summary"] = protocoltype.short_name
    calendar["prodid"] = "Protokollsystem 3"
    calendar["version"] = "2.0"
    for protocol in protocols:
        event = icalendar.Event()
        event["uid"] = protocol.id
        to_datetime = icalendar.prop.vDatetime
        start = protocol.get_timezone_aware_start_date()
        event["dtstamp"] = to_datetime(start)
        event["dtstart"] = to_datetime(start)
        event["dtend"] = to_datetime(start + timedelta(hours=3))
        event["summary"] = protocoltype.short_name
        event["description"] = "\n".join(
            top.name for top in protocol.get_tops())
        calendar.add_component(event)
    content = calendar.to_ical().decode("utf-8")
    for key in config.CALENDAR_TIMEZONE_MAP:
        content = content.replace(
            "TZID={}:".format(key),
            "TZID={}:".format(config.CALENDAR_TIMEZONE_MAP[key]))
    return Response(content.encode("utf-8"), mimetype="text/calendar")


@app.route("/like/new")
@login_required
@protect_csrf
def new_like():
    user = current_user()
    parent = None
    if "protocol_id" in request.args:
        parent = Protocol.first_by_id(request.args.get("protocol_id"))
    elif "todo_id" in request.args:
        parent = Todo.first_by_id(request.args.get("todo_id"))
    elif "decision_id" in request.args:
        parent = Decision.first_by_id(request.args.get("decision_id"))
    elif "top_id" in request.args:
        parent = TOP.first_by_id(request.args.get("top_id"))
    if parent is None or not parent.has_public_view_right(user):
        flash("Missing object to like.", "alert-error")
        return back.redirect()
    if len([like for like in parent.likes if like.who == user.username]) > 0:
        flash("You have liked this already!", "alert-error")
        return back.redirect()
    like = Like(who=user.username)
    db.session.add(like)
    parent.likes.append(like)
    db.session.commit()
    flash("Like!", "alert-success")
    return back.redirect()


@app.route("/login", methods=["GET", "POST"])
def login():
    if "auth" in session and current_user() is not None:
        flash("You are already logged in.", "alert-success")
        return redirect(url_for("index"))
    form = LoginForm()
    if form.validate_on_submit():
        user = user_manager.login(
            form.username.data, form.password.data,
            permanent=form.permanent.data)
        if user is not None:
            session["auth"] = security_manager.hash_user(user)
            session.permanent = form.permanent.data
            flash("Login successful, {}!".format(user.username),
                  "alert-success")
            return back.redirect()
        else:
            flash("Wrong login data. Try again.", "alert-error")
    return render_template("login.html", form=form)


@app.route("/logout")
@login_required
@protect_csrf
def logout():
    if "auth" in session:
        session.pop("auth")
    else:
        flash("You are not logged in.", "alert-error")
    return redirect(url_for(".index"))


try:
    from uwsgidecorators import cron as uwsgicron

    @uwsgicron(30, -1, -1, -1, -1, target="mule")
    def uwsgi_timer(signum):
        if signum == 0:
            check_and_send_reminders()

    def make_scheduler():
        pass
except ImportError as exc:
    def make_scheduler():
        scheduler = BackgroundScheduler()
        scheduler.start()
        scheduler.add_job(
            func=check_and_send_reminders,
            trigger=CronTrigger(hour='*', minute=30),
            id="scheduler",
            name="Do an action regularly",
            replace_existing=True)
        atexit.register(scheduler.shutdown)


def check_and_send_reminders():
    if not config.MAIL_ACTIVE:
        return
    with app.app_context():
        current_time = datetime.now()
        current_day = current_time.date()
        for protocol in Protocol.query.filter(not Protocol.done).all():
            day_difference = (protocol.date - current_day).days
            usual_time = protocol.get_time()
            protocol_time = datetime(
                1, 1, 1, usual_time.hour, usual_time.minute)
            hour_difference = (protocol_time - current_time).seconds // 3600
            for reminder in protocol.protocoltype.reminders:
                if (day_difference == reminder.days_before
                        and hour_difference == 0):
                    tasks.send_reminder(reminder, protocol)
            if (day_difference < 0
                    and (-day_difference
                         > config.MAX_PAST_INDEX_DAYS_BEFORE_REMINDER)
                    and hour_difference == 0):  # once per day
                tasks.remind_finishing(
                    protocol, -day_difference,
                    config.MAX_PAST_INDEX_DAYS_BEFORE_REMINDER)


if __name__ == "__main__":
    manager.run()
