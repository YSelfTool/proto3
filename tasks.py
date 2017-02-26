from flask import render_template

import os
import subprocess
import shutil
import tempfile

from models.database import Document, Protocol, Error, Todo, Decision, TOP, DefaultTOP, MeetingReminder
from models.errors import DateNotMatchingException
from server import celery, app
from shared import db, escape_tex, unhyphen, date_filter, datetime_filter, date_filter_long, date_filter_short, time_filter, class_filter
from utils import mail_manager, url_manager, encode_kwargs, decode_kwargs
from parser import parse, ParserException, Element, Content, Text, Tag, Remark, Fork, RenderType
from wiki import WikiClient, WikiException

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
                    source_lines = source.splitlines()
                    start_index = max(0, exc.linenumber - config.ERROR_CONTEXT_LINES)
                    end_index = min(len(source_lines) - 1, exc.linenumber + config.ERROR_CONTEXT_LINES)
                    context = "\n".join(source_lines[start_index:end_index])
                error = protocol.create_error("Parsing", str(exc), context)
                db.session.add(error)
                db.session.commit()
                return
            remarks = {element.name: element for element in tree.children if isinstance(element, Remark)}
            required_fields = ["Datum", "Anwesende", "Beginn", "Ende", "Autor", "Ort"]
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
                    ", ".join([remarks["Datum"], remarks["Beginn"], remarks["Ende"]])))
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
                todo = None
                field_id = None
                for other_field in todo_tag.values[2:]:
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
                        todo = Todo.query.filter_by(number=field_id).first()
                who = who.strip()
                what = what.strip()
                if todo is None:
                    if field_id is not None:
                        candidate = Todo.query.filter_by(who=who, description=what, number=None).first()
                        if candidate is None:
                            candidate = Todo.query.filter_by(description=what, number=None).first()
                        if candidate is not None:
                            candidate.number = field_id
                            todo = candidate
                        else:
                            todo = Todo(type_id=protocol.protocoltype.id, who=who, description=what, tags="", done=False)
                            todo.number = field_id
                    else:
                        candidate = Todo.query.filter_by(who=who, description=what).first()
                        if candidate is not None:
                            todo = candidate
                        else:
                            todo = Todo(type_id=protocol.protocoltype.id, who=who, description=what, tags="", done=False)
                            db.session.add(todo)
                todo.protocols.append(protocol)
                todo_tags_internal = todo.tags.split(";")
                for other_field in todo_tag.values[2:]:
                    if other_field.startswith(ID_FIELD_BEGINNING):
                        continue
                    elif other_field == "done":
                        todo.done = True
                    elif other_field not in todo_tags_internal:
                        todo_tags_internal.append(other_field)
                todo.tags = ";".join(todo_tags_internal)
                todo_tag.todo = todo
                db.session.commit()
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
                print("different")
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
    compile_async.delay(content, protocol.id, show_private)

@celery.task
def compile_async(content, protocol_id, show_private):
    with tempfile.TemporaryDirectory() as compile_dir, app.app_context():
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
            for old_document in [document for document in protocol.documents if document.is_compiled and document.is_private == show_private]:
                protocol.documents.remove(old_document)
            db.session.commit()
            document = Document(protocol.id, name="protokoll{}_{}_{}.pdf".format("_intern" if show_private else "", protocol.protocoltype.short_name, date_filter_short(protocol.date)), filename="", is_compiled=True, is_private=show_private)
            db.session.add(document)
            db.session.commit()
            target_filename = "compiled-{}-{}.pdf".format(document.id, "internal" if show_private else "public")
            document.filename = target_filename
            shutil.copy(os.path.join(compile_dir, protocol_target_filename), os.path.join(config.DOCUMENTS_PATH, target_filename))
            db.session.commit()
            #shutil.copy(os.path.join(compile_dir, log_filename), "/tmp")
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
        reminder_text = render_template("reminder.txt", reminder=reminder, protocol=protocol)
        if reminder.send_public:
            send_mail(protocol, protocol.protocoltype.public_mail, "Tagesordnung der {}".format(protocol.protocoltype.name), reminder_text)
        if reminder.send_private:
            send_mail(protocol, protocol.protocoltype.private_mail, "Tagesordnung der {}".format(protocol.protocoltype.name), reminder_text)

def send_mail(protocol, to_addr, subject, content):
    if to_addr is not None and len(to_addr.strip()) > 0:
        send_mail_async.delay(protocol.id, to_addr, subject, content)

@celery.task
def send_mail_async(protocol_id, to_addr, subject, content):
    with app.app_context():
        protocol = Protocol.query.filter_by(id=protocol_id).first()
        try:
            print("sending {} to {}".format(subject, to_addr))
            mail_manager.send(to_addr, subject, content)
        except Exception as exc:
            error = protocol.create_error("Sending Mail", "Sending mail failed", str(exc))
            db.session.add(error)
            db.session.commit()

