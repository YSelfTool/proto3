from flask import render_template

import os
import subprocess
import shutil
import tempfile

from models.database import Document, Protocol, Error, Todo, Decision, TOP, DefaultTOP
from server import celery, app
from shared import db, escape_tex, unhyphen, date_filter, datetime_filter, date_filter_long, time_filter
from utils import mail_manager, url_manager, encode_kwargs, decode_kwargs
from parser import parse, ParserException, Element, Content, Text, Tag, Remark, Fork

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
texenv.filters["datetimify"] = datetime_filter
texenv.filters["timify"] = time_filter

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
                for other_field in todo_tag.values[2:]:
                    if other_field.startswith(ID_FIELD_BEGINNING):
                        field_id = 0
                        try:
                            field_id = int(other_field[len(ID_FIELD_BEGINNING):])
                        except ValueError:
                            error = protocol.create_error("Parsing", "Non-numerical todo ID",
                            "The todo in line {} has a nonnumerical ID, but needs "
                            "something like \"id 1234\"".format(todo_tag.linenumber))
                            db.session.add(error)
                            db.session.commit()
                            return
                        todo = Todo.query.filter_by(id=field_id).first()
                if todo is None:
                    todo = Todo(who=who, description=what, tags="", done=False)
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

            latex_source = texenv.get_template("protocol.tex").render(protocol=protocol, tree=tree)
            compile(latex_source, protocol)

            protocol.done = True
            db.session.commit()

def compile(content, protocol):
    compile_async.delay(content, protocol.id)

@celery.task
def compile_async(content, protocol_id):
    with tempfile.TemporaryDirectory() as compile_dir, app.app_context():
        protocol = Protocol.query.filter_by(id=protocol_id).first()
        try:
            current = os.getcwd()
            protocol_source_filename = "protocol.tex"
            protocol_target_filename = "protocol.tex"
            log_filename = "protocol.log"
            with open(os.path.join(compile_dir, protocol_source_filename), "w") as source_file:
                source_file.write(content)
            shutil.copy("static/tex/protokoll2.cls", compile_dir)
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
            document = Document(protocol.id, name="protokoll_{}_{}.pdf".format(protocol.protocoltype.short_name, date_filter(protocol.date)), filename="", is_compiled=True)
            db.session.add(document)
            db.session.commit()
            target_filename = "compiled-{}.pdf".format(document.id)
            document.filename = target_filename
            shutil.copy(os.path.join(compile_dir, protocol_target_filename), os.path.join("documents", target_filename))
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

def send_mail(mail):
    send_mail_async.delay(mail.id)

@celery.task
def send_mail_async(mail_id):
    with app.app_context():
        mail = Mail.query.filter_by(id=mail_id).first()
        if mail is None:
            return False
        mail.ready = False
        mail.error = False
        db.session.commit()
        result = mail_manager.send(mail.to_addr, mail.subject, mail.content)
        mail.ready = True
        mail.error = not result
        db.session.commit()


