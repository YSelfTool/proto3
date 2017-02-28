from flask import render_template

import os
import subprocess
import shutil
import tempfile
from datetime import datetime

from models.database import Document, Protocol, Error, Todo, Decision, TOP, DefaultTOP, MeetingReminder, TodoMail, DecisionDocument, TodoState, OldTodo
from models.errors import DateNotMatchingException
from server import celery, app
from shared import db, escape_tex, unhyphen, date_filter, datetime_filter, date_filter_long, date_filter_short, time_filter, class_filter, KNOWN_KEYS
from utils import mail_manager, url_manager, encode_kwargs, decode_kwargs
from parser import parse, ParserException, Element, Content, Text, Tag, Remark, Fork, RenderType
from wiki import WikiClient, WikiException
from calendarpush import Client as CalendarClient, CalendarException
from legacy import lookup_todo_id, import_old_todos

import config

texenv = app.create_jinja_environment()
texenv.block_start_string = r"\ENV{"
texenv.block_end_string = r"}"
texenv.variable_start_string = r"\VAR{"
texenv.variable_end_string = r"}"
texenv.comment_start_string = r"\COMMENT{"
texenv.comment_end_string = r"}"
texenv.filters["escape_tex"] = escape_tex
texenv.filters["unhyphen"] = unhyphen
texenv.trim_blocks = True
texenv.lstrip_blocks = True
texenv.filters["url_complete"] = url_manager.complete
texenv.filters["datify"] = date_filter
texenv.filters["datify_long"] = date_filter_long
texenv.filters["datify_short"] = date_filter_short
texenv.filters["datetimify"] = datetime_filter
texenv.filters["timify"] = time_filter
texenv.filters["class"] = class_filter

mailenv = app.create_jinja_environment()
mailenv.trim_blocks = True
mailenv.lstrip_blocks = True
mailenv.filters["url_complete"] = url_manager.complete
mailenv.filters["datify"] = date_filter
mailenv.filters["datetimify"] = datetime_filter

ID_FIELD_BEGINNING = "id "

def parse_protocol(protocol, **kwargs):
    parse_protocol_async.delay(protocol.id, encode_kwargs(kwargs))

@celery.task
def parse_protocol_async(protocol_id, encoded_kwargs):
    with app.app_context():
        with app.test_request_context("/"):
            kwargs = decode_kwargs(encoded_kwargs)
            protocol = Protocol.query.filter_by(id=protocol_id).first()
            if protocol is None:
                raise Exception("No protocol given. Aborting parsing.")
            old_errors = list(protocol.errors)
            for error in old_errors:
                protocol.errors.remove(error)
            db.session.commit()
            if protocol.source is None:
                error = protocol.create_error("Parsing", "Protocol source is None", "")
                db.session.add(error)
                db.session.commit()
                return
            tree = None
            try:
                tree = parse(protocol.source)
            except ParserException as exc:
                context = ""
                if exc.linenumber is not None:
                    source_lines = protocol.source.splitlines()
                    start_index = max(0, exc.linenumber - config.ERROR_CONTEXT_LINES)
                    end_index = min(len(source_lines) - 1, exc.linenumber + config.ERROR_CONTEXT_LINES)
                    context = "\n".join(source_lines[start_index:end_index])
                if exc.tree is not None:
                    context += "\n\nParsed syntax tree was:\n" + str(exc.tree.dump())
                error = protocol.create_error("Parsing", str(exc), context)
                db.session.add(error)
                db.session.commit()
                return
            remarks = {element.name: element for element in tree.children if isinstance(element, Remark)}
            required_fields = KNOWN_KEYS
            if not config.PARSER_LAZY:
                missing_fields = [field for field in required_fields if field not in remarks]
                if len(missing_fields) > 0:
                    error = protocol.create_error("Parsing", "Missing fields", ", ".join(missing_fields))
                    db.session.add(error)
                    db.session.commit()
                    return
            try:
                protocol.fill_from_remarks(remarks)
            except ValueError:
                error = protocol.create_error(
                    "Parsing", "Invalid fields",
                    "Date or time fields are not '%d.%m.%Y' respectively '%H:%M', "
                    "but rather {}".format(
                    ", ".join([
                        remarks["Datum"].value.strip(),
                        remarks["Beginn"].value.strip(),
                        remarks["Ende"].value.strip()
                    ])))
                db.session.add(error)
                db.session.commit()
                return
            except DateNotMatchingException as exc:
                error = protocol.create_error("Parsing", "Date not matching",
                    "This protocol's date should be {}, but the protocol source says {}.".format(date_filter(exc.original_date), date_filter(exc.protocol_date)))
                db.session.add(error)
                db.session.commit()
                return
            protocol.delete_orphan_todos()
            db.session.commit()
            old_todos = list(protocol.todos)
            for todo in old_todos:
                protocol.todos.remove(todo)
            db.session.commit()
            tags = tree.get_tags()
            # todos
            todo_tags = [tag for tag in tags if tag.name == "todo"]
            for todo_tag in todo_tags:
                if len(todo_tag.values) < 2:
                    error = protocol.create_error("Parsing", "Invalid todo-tag",
                        "The todo tag in line {} needs at least "
                        "information on who and what, "
                        "but has less than that.".format(todo_tag.linenumber))
                    db.session.add(error)
                    db.session.commit()
                    return
                who = todo_tag.values[0]
                what = todo_tag.values[1]
                field_id = None
                field_state = None
                field_date = None
                for other_field in todo_tag.values[2:]:
                    if len(other_field) == 0:
                        continue
                    if other_field.startswith(ID_FIELD_BEGINNING):
                        try:
                            field_id = int(other_field[len(ID_FIELD_BEGINNING):])
                        except ValueError:
                            error = protocol.create_error("Parsing", "Non-numerical todo ID",
                            "The todo in line {} has a nonnumerical ID, but needs "
                            "something like \"id 1234\"".format(todo_tag.linenumber))
                            db.session.add(error)
                            db.session.commit()
                            return
                    else:
                        try:
                            field_state = TodoState.from_name(other_field.strip())
                        except ValueError:
                            try:
                                field_date = datetime.strptime(other_field.strip(), "%d.%m.%Y")
                            except ValueError:
                                error = protocol.create_error("Parsing",
                                "Invalid field",
                                "The todo in line {} has the field '{}', but"
                                "this does neither match a date (\"%d.%m.%Y\")"
                                "nor a state.".format(
                                    todo_tag.linenumber, other_field))
                                db.session.add(error)
                                db.session.commit()
                                return
                if field_state is None:
                    field_state = TodoState.open
                if field_state.needs_date() and field_date is None:
                    error = protocol.create_error("Parsing",
                        "Todo missing date",
                        "The todo in line {} has a state that needs a date, "
                        "but the todo does not have one.".format(todo_tag.line))
                    db.session.add(error)
                    db.session.commit()
                    return
                who = who.strip()
                what = what.strip()
                todo = None
                if field_id is not None:
                    todo = Todo.query.filter_by(number=field_id).first()
                    if todo is None and not config.PARSER_LAZY:
                        # TODO: add non-strict mode (at least for importing old protocols)
                        error = protocol.create_error("Parsing",
                        "Invalid Todo ID",
                        "The todo in line {} has the ID {}, but there is no "
                        "Todo with that ID.".format(todo_tag.linenumber, field_id))
                        db.session.add(error)
                        db.session.commit()
                        return
                if todo is None:
                    protocol_key = protocol.get_identifier()
                    old_candidates = OldTodo.query.filter(
                        OldTodo.protocol_key == protocol_key).all()
                    if len(old_candidates) == 0:
                        # new protocol
                        todo = Todo(type_id=protocol.protocoltype.id,
                            who=who, description=what, state=field_state,
                            date=field_date)
                        db.session.add(todo)
                        db.session.commit()
                        todo.number = field_id or todo.id
                        db.session.commit()
                    else:
                        # old protocol
                        number = field_id or lookup_todo_id(old_candidates, who, what)
                        todo = Todo.query.filter_by(number=number).first()
                        if todo is None:
                            todo = Todo(type_id=protocol.protocoltype.id,
                                who=who, description=what, state=field_state,
                                date=field_date, number=number)
                            db.session.add(todo)
                            db.session.commit()
                todo.protocols.append(protocol)
                db.session.commit()
                todo_tag.todo = todo
            # Decisions
            old_decisions = list(protocol.decisions)
            for decision in old_decisions:
                protocol.decisions.remove(decision)
            db.session.commit()
            decision_tags = [tag for tag in tags if tag.name == "beschluss"]
            for decision_tag in decision_tags:
                if len(decision_tag.values) == 0:
                    error = protocol.create_error("Parsing", "Empty decision found.",
                        "The decision in line {} is empty.".format(decision_tag.linenumber))
                    db.session.add(error)
                    db.session.commit()
                    return
                decision = Decision(protocol_id=protocol.id, content=decision_tag.values[0])
                db.session.add(decision)
                db.session.commit()
                decision_content = texenv.get_template("decision.tex").render(render_type=RenderType.latex, decision=decision, protocol=protocol, top=decision_tag.fork.get_top(), show_private=False)
                compile_decision(decision_content, decision)
            old_tops = list(protocol.tops)
            for top in old_tops:
                protocol.tops.remove(top)
            tops = []
            for index, fork in enumerate((child for child in tree.children if isinstance(child, Fork))):
                top = TOP(protocol.id, fork.name, index, False)
                db.session.add(top)
            db.session.commit()

            render_kwargs = {
                "protocol": protocol,
                "tree": tree
            }
            privacy_states = [False]
            content_private = render_template("protocol.txt", render_type=RenderType.plaintext, show_private=True, **render_kwargs)
            content_public = render_template("protocol.txt", render_type=RenderType.plaintext, show_private=False, **render_kwargs)
            if content_private != content_public:
                privacy_states.append(True)
            protocol.content_private = content_private
            protocol.content_public = content_public

            for show_private in privacy_states:
                latex_source = texenv.get_template("protocol.tex").render(render_type=RenderType.latex, show_private=show_private, **render_kwargs)
                compile(latex_source, protocol, show_private=show_private)

            if protocol.protocoltype.use_wiki:
                wiki_source = render_template("protocol.wiki", render_type=RenderType.wikitext, show_private=not protocol.protocoltype.wiki_only_public, **render_kwargs).replace("\n\n\n", "\n\n")
                push_to_wiki(protocol, wiki_source, "Automatisch generiert vom Protokollsystem 3.0")
            protocol.done = True
            db.session.commit()

def push_to_wiki(protocol, content, summary):
    push_to_wiki_async.delay(protocol.id, content, summary)

@celery.task
def push_to_wiki_async(protocol_id, content, summary):
    with WikiClient() as wiki_client, app.app_context():
        protocol = Protocol.query.filter_by(id=protocol_id).first()
        try:
            wiki_client.edit_page(
                title=protocol.get_wiki_title(),
                content=content,
                summary="Automatisch generiert vom Protokollsystem 3.")
        except WikiException as exc:
            error = protocol.create_error("Pushing to Wiki", "Pushing to Wiki failed.", str(exc))

def compile(content, protocol, show_private):
   compile_async.delay(content, protocol.id, show_private=show_private)

def compile_decision(content, decision):
    compile_async.delay(content, decision.id, use_decision=True)

@celery.task
def compile_async(content, protocol_id, show_private=False, use_decision=False):
    with tempfile.TemporaryDirectory() as compile_dir, app.app_context():
        decision = None
        protocol = None
        if use_decision:
            decision = Decision.query.filter_by(id=protocol_id).first()
            protocol = decision.protocol
        else:
            protocol = Protocol.query.filter_by(id=protocol_id).first()
        try:
            current = os.getcwd()
            protocol_source_filename = "protocol.tex"
            protocol_target_filename = "protocol.pdf"
            log_filename = "protocol.log"
            with open(os.path.join(compile_dir, protocol_source_filename), "w") as source_file:
                source_file.write(content)
            protocol2_class_source = texenv.get_template("protokoll2.cls").render(fonts=config.FONTS)
            with open(os.path.join(compile_dir, "protokoll2.cls"), "w") as protocol2_class_file:
                protocol2_class_file.write(protocol2_class_source)
            os.chdir(compile_dir)
            command = [
                "/usr/bin/xelatex",
                "-halt-on-error",
                "-file-line-error",
                protocol_source_filename
            ]
            subprocess.check_call(command, universal_newlines=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            subprocess.check_call(command, universal_newlines=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            os.chdir(current)
            document = None
            if not use_decision:
                for old_document in [document for document in protocol.documents if document.is_compiled and document.is_private == show_private]:
                    protocol.documents.remove(old_document)
                db.session.commit()
                document = Document(protocol.id, name="protokoll{}_{}_{}.pdf".format("_intern" if show_private else "", protocol.protocoltype.short_name, date_filter_short(protocol.date)), filename="", is_compiled=True, is_private=show_private)
            else:
                document = DecisionDocument(decision.id, name="beschluss_{}_{}_{}.pdf".format(protocol.protocoltype.short_name, date_filter_short(protocol.date), decision.id), filename="")
            db.session.add(document)
            db.session.commit()
            target_filename = "compiled-{}-{}.pdf".format(document.id, "internal" if show_private else "public")
            if use_decision:
                target_filename = "decision-{}-{}-{}.pdf".format(protocol.id, decision.id, document.id)
            document.filename = target_filename
            shutil.copy(os.path.join(compile_dir, protocol_target_filename), os.path.join(config.DOCUMENTS_PATH, target_filename))
            db.session.commit()
        except subprocess.SubprocessError:
            log = ""
            total_log_filename = os.path.join(compile_dir, log_filename)
            if os.path.isfile(total_log_filename):
                with open(total_log_filename, "r") as log_file:
                    log = log_file.read()
            else:
                log = "Logfile not found."
            error = protocol.create_error("Compiling", "Compiling LaTeX failed", log)
            db.session.add(error)
            db.session.commit()
        finally:
            os.chdir(current)

def print_file(filename, protocol):
    if config.PRINTING_ACTIVE:
        print_file_async.delay(filename, protocol.id)

@celery.task
def print_file_async(filename, protocol_id):
    with app.app_context():
        protocol = Protocol.query.filter_by(id=protocol_id).first()
        if protocol.protocoltype.printer is None:
            error = protocol.create_error("Printing", "No printer configured.", "You don't have any printer configured for the protocoltype {}. Please do so before printing a protocol.".format(protocol.protocoltype.name))
        try:
            command = [
                "/usr/bin/lpr",
                "-H", config.PRINTING_SERVER,
                "-P", protocol.protocoltype.printer,
                "-U", config.PRINTING_USER,
                "-T", protocol.get_identifier(),
            ]
            for option in config.PRINTING_PRINTERS[protocol.protocoltype.printer]:
                command.extend(["-o", '"{}"'.format(option) if " " in option else option])
            command.append(filename)
            subprocess.check_call(command, universal_newlines=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except subprocess.SubprocessError:
            error = protocol.create_error("Printing", "Printing {} failed.".format(protocol.get_identifier()), "")
            db.session.add(error)
            db.session.commit()

def send_reminder(reminder, protocol):
    send_reminder_async.delay(reminder.id, protocol.id)

@celery.task
def send_reminder_async(reminder_id, protocol_id):
    with app.app_context():
        reminder = MeetingReminder.query.filter_by(id=reminder_id).first()
        protocol = Protocol.query.filter_by(id=protocol_id).first()
        reminder_text = render_template("reminder-mail.txt", reminder=reminder, protocol=protocol)
        if reminder.send_public:
            send_mail(protocol, protocol.protocoltype.public_mail, "Tagesordnung der {}".format(protocol.protocoltype.name), reminder_text)
        if reminder.send_private:
            send_mail(protocol, protocol.protocoltype.private_mail, "Tagesordnung der {}".format(protocol.protocoltype.name), reminder_text)

def send_protocol(protocol):
    send_protocol_async.delay(protocol.id, show_private=True)
    send_protocol_async.delay(protocol.id, show_private=False)
    send_todomails_async.delay(protocol.id)

@celery.task
def send_protocol_async(protocol_id, show_private):
    with app.app_context():
        protocol = Protocol.query.filter_by(id=protocol_id).first()
        to_addr = protocol.protocoltype.private_mail if show_private else protocol.protocoltype.public_mail
        subject = "{}{}-Protokoll vom {}".format("Internes " if show_private else "", protocol.protocoltype.short_name, date_filter(protocol.date))
        mail_content = render_template("protocol-mail.txt", protocol=protocol)
        appendix = [(document.name, document.as_file_like())
            for document in protocol.documents
            if show_private or not document.is_private
        ]
        send_mail(protocol, to_addr, subject, mail_content, appendix)

@celery.task
def send_todomails_async(protocol_id):
    with app.app_context():
        protocol = Protocol.query.filter_by(id=protocol_id).first()
        all_todos = Todo.query.filter(Todo.done == False).all()
        users = {user for todo in all_todos for user in todo.get_users()}
        grouped_todos = {
            user: [todo for todo in all_todos if user in todo.get_users()]
            for user in users
        }
        subject = "Du hast noch was zu tun!"
        for user in users:
            todomail = TodoMail.query.filter(TodoMail.name.ilike(user)).first()
            if todomail is None:
                error = protocol.create_error("Sending Todomail", "Sending Todomail failed.", "User {} has no Todo-Mail-Assignment.".format(user))
                db.session.add(error)
                db.session.commit()
                continue
            to_addr = todomail.get_formatted_mail()
            mail_content = render_template("todo-mail.txt", protocol=protocol, todomail=todomail, todos=grouped_todos[user])
            send_mail(protocol, to_addr, subject, mail_content)

def send_mail(protocol, to_addr, subject, content, appendix=None):
    if to_addr is not None and len(to_addr.strip()) > 0:
        send_mail_async.delay(protocol.id, to_addr, subject, content, appendix)

@celery.task
def send_mail_async(protocol_id, to_addr, subject, content, appendix):
    with app.app_context():
        protocol = Protocol.query.filter_by(id=protocol_id).first()
        try:
            mail_manager.send(to_addr, subject, content, appendix)
        except Exception as exc:
            error = protocol.create_error("Sending Mail", "Sending mail failed", str(exc))
            db.session.add(error)
            db.session.commit()

def push_tops_to_calendar(protocol):
    push_tops_to_calendar_async.delay(protocol.id)

@celery.task
def push_tops_to_calendar_async(protocol_id):
    if not config.CALENDAR_ACTIVE:
        return
    with app.app_context():
        protocol = Protocol.query.filter_by(id=protocol_id).first()
        if protocol.protocoltype.calendar == "":
            return
        description = render_template("calendar-tops.txt", protocol=protocol)
        try:
            client = CalendarClient(protocol.protocoltype.calendar)
            client.set_event_at(begin=protocol.get_datetime(),
                name=protocol.protocoltype.short_name, description=description)
        except CalendarException as exc:
            error = Protocol.create_error("Calendar",
                "Pushing TOPs to Calendar failed", str(exc))
            db.session.add(error)
            db.session.commit()
