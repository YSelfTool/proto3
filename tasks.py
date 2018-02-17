from flask import render_template

import os
import subprocess
import shutil
import tempfile
from datetime import datetime
import traceback
from copy import copy
import xmlrpc.client

from models.database import Document, Protocol, Error, Todo, Decision, TOP, DefaultTOP, MeetingReminder, TodoMail, DecisionDocument, TodoState, OldTodo, DecisionCategory
from models.errors import DateNotMatchingException
from server import celery, app
from shared import db, escape_tex, unhyphen, date_filter, datetime_filter, date_filter_long, date_filter_short, time_filter, class_filter, KNOWN_KEYS, WikiType
from utils import mail_manager, encode_kwargs, decode_kwargs, add_line_numbers, set_etherpad_text, get_etherpad_text, footnote_hash, parse_datetime_from_string
from protoparser import parse, ParserException, Element, Content, Text, Tag, Remark, Fork, RenderType
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
#texenv.filters["url_complete"] = url_manager.complete
texenv.filters["datify"] = date_filter
texenv.filters["datify_long"] = date_filter_long
texenv.filters["datify_short"] = date_filter_short
texenv.filters["datetimify"] = datetime_filter
texenv.filters["timify"] = time_filter
texenv.filters["class"] = class_filter
logo_template = getattr(config, "LATEX_LOGO_TEMPLATE", None)
if logo_template is not None:
    texenv.globals["logo_template"] = logo_template
latex_geometry = getattr(config, "LATEX_GEOMETRY", "vmargin=1.5cm,hmargin={1.5cm,1.2cm},bindingoffset=8mm")
texenv.globals["latex_geometry"] = latex_geometry
raw_additional_packages = getattr(config, "LATEX_ADDITIONAL_PACKAGES", None)
additional_packages = []
if raw_additional_packages is not None:
    for package in raw_additional_packages:
        if "{" not in package:
            package = "{{{}}}".format(package)
        additional_packages.append(package)
texenv.globals["additional_packages"] = additional_packages
latex_pagestyle = getattr(config, "LATEX_PAGESTYLE", None)
if latex_pagestyle is not None and latex_pagestyle:
    texenv.globals["latex_pagestyle"] = latex_pagestyle
latex_header_footer = getattr(config, "LATEX_HEADER_FOOTER", False)
texenv.globals["latex_header_footer"] = latex_header_footer

mailenv = app.create_jinja_environment()
mailenv.trim_blocks = True
mailenv.lstrip_blocks = True
#mailenv.filters["url_complete"] = url_manager.complete
mailenv.filters["datify"] = date_filter
mailenv.filters["datetimify"] = datetime_filter

wikienv = app.create_jinja_environment()
wikienv.trim_blocks = True
wikienv.lstrip_blocks = True
wikienv.block_start_string = "<env>"
wikienv.block_end_string = "</env>"
wikienv.variable_start_string = "<var>"
wikienv.variable_end_string = "</var>"
wikienv.comment_start_string = "<comment>"
wikienv.comment_end_string = "</comment>"
wikienv.filters["datify"] = date_filter
wikienv.filters["datify_long"] = date_filter_long
wikienv.filters["datify_short"] = date_filter_short
wikienv.filters["datetimify"] = datetime_filter
wikienv.filters["timify"] = time_filter
wikienv.filters["class"] = class_filter


ID_FIELD_BEGINNING = "id "

def parse_protocol(protocol, **kwargs):
    parse_protocol_async.delay(protocol.id, encode_kwargs(kwargs))

@celery.task
def parse_protocol_async(protocol_id, encoded_kwargs):
    with app.app_context():
        with app.test_request_context("/"):
            try:
                kwargs = decode_kwargs(encoded_kwargs)
                protocol = Protocol.query.filter_by(id=protocol_id).first()
                if protocol is None:
                    raise Exception("No protocol given. Aborting parsing.")
                parse_protocol_async_inner(protocol, encoded_kwargs)
            except Exception as exc:
                stacktrace = traceback.format_exc()
                error = protocol.create_error("Parsing", "Exception",
                    "{}\n\n{}".format(str(exc), stacktrace))
                db.session.add(error)
                db.session.commit()

def parse_protocol_async_inner(protocol, encoded_kwargs):
    old_errors = list(protocol.errors)
    for error in old_errors:
        protocol.errors.remove(error)
    db.session.commit()
    if protocol.source is None or len(protocol.source.strip()) == 0:
        error = protocol.create_error("Parsing", "Protocol source is empty", "")
        db.session.add(error)
        db.session.commit()
        return
    if protocol.source == config.EMPTY_ETHERPAD:
        error = protocol.create_error("Parsing", "The etherpad is unmodified and does not contain a protocol.", protocol.source)
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
    required_fields = copy(KNOWN_KEYS)
    for default_meta in protocol.protocoltype.metas:
        required_fields.append(default_meta.key)
    if not config.PARSER_LAZY:
        missing_fields = [field for field in required_fields if field not in remarks]
        if len(missing_fields) > 0:
            error = protocol.create_error("Parsing", "Du hast vergessen, Metadaten anzugeben.", ", ".join(missing_fields))
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
            "This protocol's date should be {}, but the protocol source says {}.".format(date_filter(exc.original_date) if exc.original_date is not None else "not present", date_filter(exc.protocol_date) if exc.protocol_date is not None else "not present"))
        db.session.add(error)
        db.session.commit()
        return
    # tags 
    tags = tree.get_tags()
    elements = tree.get_visible_elements(show_private=True)
    public_elements = tree.get_visible_elements(show_private=False)
    for tag in tags:
        if tag.name not in Tag.KNOWN_TAGS:
            error = protocol.create_error("Parsing", "Invalid tag",
                "The tag in line {} has the kind '{}', which is "
                "not defined. This is probably an error mit a missing "
                "semicolon.".format(tag.linenumber, tag.name))
            db.session.add(error)
            db.session.commit()
            return
    # todos
    old_todo_number_map = {}
    for todo in protocol.todos:
        old_todo_number_map[todo.description] = todo.get_id()
    protocol.delete_orphan_todos()
    db.session.commit()
    old_todos = list(protocol.todos)
    todo_tags = [tag for tag in tags if tag.name == "todo"]
    raw_todos = []
    for todo_tag in todo_tags:
        if len(todo_tag.values) < 2:
            error = protocol.create_error("Parsing", "Invalid todo-tag",
                "The todo tag in line {} needs at least "
                "information on who and what, "
                "but has less than that. This is probably "
                "a missing semicolon.".format(todo_tag.linenumber))
            db.session.add(error)
            db.session.commit()
            return
        who = todo_tag.values[0]
        what = todo_tag.values[1]
        field_id = None
        field_state = None
        field_date = None
        for other_field in todo_tag.values[2:]:
            other_field = other_field.strip()
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
                    field_state = TodoState.from_name(other_field)
                except ValueError:
                    try:
                        field_date = datetime.strptime(other_field, "%d.%m.%Y")
                    except ValueError:
                        try:
                            field_state, field_date = TodoState.from_name_with_date(other_field.strip(), protocol=protocol)
                        except ValueError:
                            try:
                                field_state = TodoState.from_name_lazy(other_field)
                            except ValueError:
                                error = protocol.create_error("Parsing",
                                "Invalid field",
                                "The todo in line {} has the field '{}', but "
                                "this does neither match a date (\"%d.%m.%Y\") "
                                "nor a state.".format(
                                    todo_tag.linenumber, other_field))
                                db.session.add(error)
                                db.session.commit()
                                return
        raw_todos.append((who, what, field_id, field_state, field_date, todo_tag))
    for (_, _, field_id, _, _, _) in raw_todos:
        if field_id is not None:
            old_todos = [todo for todo in old_todos
                if todo.id != field_id]
    for todo in old_todos:
        protocol.todos.remove(todo)
    db.session.commit()
    for (who, what, field_id, field_state, field_date, todo_tag) in raw_todos:
        if field_state is None:
            field_state = TodoState.open
        if field_state.needs_date() and field_date is None:
            error = protocol.create_error("Parsing",
                "Todo missing date",
                "The todo in line {} has a state that needs a date, "
                "but the todo does not have one.".format(todo_tag.linenumber))
            db.session.add(error)
            db.session.commit()
            return
        who = who.strip()
        what = what.strip()
        todo = None
        if field_id is not None:
            todo = Todo.query.filter_by(number=field_id).first()
            if todo is None and not config.PARSER_LAZY:
                error = protocol.create_error("Parsing",
                "Invalid Todo ID",
                "The todo in line {} has the ID {}, but there is no "
                "Todo with that ID.".format(todo_tag.linenumber, field_id))
                db.session.add(error)
                db.session.commit()
                return
        if todo is None and field_id is None and what in old_todo_number_map:
            todo = Todo(protocoltype_id=protocol.protocoltype.id,
                who=who, description=what, state=field_state,
                date=field_date, number=old_todo_number_map[what])
            db.session.add(todo)
            db.session.commit()
        if todo is None:
            protocol_key = protocol.get_identifier()
            old_candidates = OldTodo.query.filter(
                OldTodo.protocol_key == protocol_key).all()
            if len(old_candidates) == 0:
                # new protocol
                todo = Todo(protocoltype_id=protocol.protocoltype.id,
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
                    todo = Todo(protocoltype_id=protocol.protocoltype.id,
                        who=who, description=what, state=field_state,
                        date=field_date, number=number)
                    db.session.add(todo)
                    db.session.commit()
        todo.protocols.append(protocol)
        is_newest_protocol = True
        for other_protocol in todo.protocols:
            if other_protocol.date > protocol.date:
                is_newest_protocol = False
                break
        if is_newest_protocol:
            todo.state = field_state
            todo.date = field_date
            todo.who = who
            todo.description = what
        db.session.commit()
        todo_tag.todo = todo
    # Decisions
    decision_tags = [tag for tag in tags if tag.name == "beschluss"]
    for decision_tag in decision_tags:
        if decision_tag not in public_elements:
            error = protocol.create_error("Parsing", "Decision in private context.",
                "The decision in line {} is in a private context, but decisions are "
                "and have to be public. Please move it to a public spot.".format(
                decision_tag.linenumber))
            db.session.add(error)
            db.session.commit()
            return
    old_decisions = list(protocol.decisions)
    for decision in old_decisions:
        protocol.decisions.remove(decision)
    db.session.commit()
    decisions_to_render = []
    for decision_tag in decision_tags:
        if len(decision_tag.values) == 0:
            error = protocol.create_error("Parsing", "Empty decision found.",
                "The decision in line {} is empty.".format(decision_tag.linenumber))
            db.session.add(error)
            db.session.commit()
            return
        decision_content = decision_tag.values[0]
        decision_categories = []
        for decision_category_name in decision_tag.values[1:]:
            decision_category = DecisionCategory.query.filter_by(protocoltype_id=protocol.protocoltype.id, name=decision_category_name).first()
            if decision_category is None:
                category_candidates = DecisionCategory.query.filter_by(protocoltype_id=protocol.protocoltype.id).all()
                category_names = [
                    "'{}'".format(category.name)
                    for category in category_candidates
                ]
                error = protocol.create_error("Parsing",
                    "Unknown decision category",
                    "The decision in line {} has the category {}, "
                    "but there is no such category. "
                    "Known categories are {}".format(
                        decision_tag.linenumber,
                        decision_category_name,
                        ", ".join(category_names)))
                db.session.add(error)
                db.session.commit()
                return
            else:
                decision_categories.append(decision_category)
        decision = Decision(protocol_id=protocol.id,
            content=decision_content)
        db.session.add(decision)
        db.session.commit()
        for decision_category in decision_categories:
            decision.categories.append(decision_category)
        decision_tag.decision = decision
        decisions_to_render.append((decision, decision_tag))
    for decision, decision_tag in decisions_to_render:
        decision_top = decision_tag.fork.get_top()
        decision_content = texenv.get_template("decision.tex").render(
            render_type=RenderType.latex, decision=decision,
            protocol=protocol, top=decision_top, show_private=True)
        maxdepth = decision_top.get_maxdepth()
        compile_decision(decision_content, decision, maxdepth=maxdepth)

    # Footnotes
    footnote_tags = [tag for tag in tags if tag.name == "footnote"]
    public_footnote_tags = [tag for tag in footnote_tags if tag in public_elements]

    # new Protocols
    protocol_tags = [tag for tag in tags if tag.name == "sitzung"]
    for protocol_tag in protocol_tags:
        if len(protocol_tag.values) not in {1, 2}:
            error = protocol.create_error("Parsing",
                "Falsche Verwendung von [sitzung;…].",
                "Der Tag \"sitzung\" benötigt immer ein Datum "
                "und optional eine Uhrzeit, also ein bis zwei Argumente. "
                "Stattdessen wurden {} übergeben, nämlich {}".format(
                len(protocol_tag.values),
                protocol_tag.values))
            db.session.add(error)
            db.ession.commit()
            return
        else:
            try:
                protocol_date = parse_datetime_from_string(
                    protocol_tag.values[0])
            except ValueError as exc:
                error = protocol.create_error("Parsing", "Invalides Datum",
                    "'{}' ist kein valides Datum.".format(
                        protocol_tag.values[0]))
                db.session.add(error)
                db.session.commit()
                return
            if len(protocol_tag.values) > 1:
                try:
                    protocol_time = datetime.strptime(protocol_tag.values[1], "%H:%M")
                except ValueError:
                    error = protocol.create_error("Parsing", "Invalide Uhrzeit",
                        "'{}' ist keine valide Uhrzeit.".format(
                            protocol_tag.values[1]))
                    db.session.add(error)
                    db.session.commit()
                    return
    for protocol_tag in protocol_tags:
        new_protocol_date = parse_datetime_from_string(protocol_tag.values[0])
        new_protocol_time = None
        if len(protocol_tag.values) > 1:
            new_protocol_time = datetime.strptime(protocol_tag.values[1], "%H:%M")
        Protocol.create_new_protocol(protocol.protocoltype,
            new_protocol_date, new_protocol_time)

    # TOPs
    old_tops = list(protocol.tops)
    for top in old_tops:
        protocol.tops.remove(top)
    tops = []
    for index, fork in enumerate((child for child in tree.children if isinstance(child, Fork))):
        top = TOP(protocol_id=protocol.id, name=fork.name, number=index,
            planned=False)
        db.session.add(top)
    db.session.commit()

    # render
    private_render_kwargs = {
        "protocol": protocol,
        "tree": tree,
        "footnotes": footnote_tags,
    }
    public_render_kwargs = copy(private_render_kwargs)
    public_render_kwargs["footnotes"] = public_footnote_tags
    render_kwargs = {True: private_render_kwargs, False: public_render_kwargs}
    
    maxdepth = tree.get_maxdepth()
    privacy_states = [False]
    content_private = render_template("protocol.txt", render_type=RenderType.plaintext, show_private=True, **private_render_kwargs)
    content_public = render_template("protocol.txt", render_type=RenderType.plaintext, show_private=False, **public_render_kwargs)
    if content_private != content_public:
        privacy_states.append(True)
    protocol.content_private = content_private
    protocol.content_public = content_public
    protocol.content_html_private = render_template("protocol.html",
        render_type=RenderType.html, show_private=True, **private_render_kwargs)
    protocol.content_html_public = render_template("protocol.html",
        render_type=RenderType.html, show_private=False, **public_render_kwargs)

    for show_private in privacy_states:
        latex_source = texenv.get_template("protocol.tex").render(
            render_type=RenderType.latex,
            show_private=show_private,
            **render_kwargs[show_private])
        compile(latex_source, protocol, show_private=show_private, maxdepth=maxdepth)

    if protocol.protocoltype.use_wiki:
        wiki_type = WikiType[getattr(config, "WIKI_TYPE", "MEDIAWIKI")]
        wiki_template = {
            WikiType.MEDIAWIKI: "protocol.wiki",
            WikiType.DOKUWIKI: "protocol.dokuwiki",
        }
        wiki_render_type = {
            WikiType.MEDIAWIKI: RenderType.wikitext,
            WikiType.DOKUWIKI: RenderType.dokuwiki,
        }
        show_private = not protocol.protocoltype.wiki_only_public
        wiki_source = wikienv.get_template(wiki_template[wiki_type]).render(
            render_type=wiki_render_type[wiki_type],
            show_private=show_private,
            **render_kwargs[show_private]
        ).replace("\n\n\n", "\n\n")
        if wiki_type == WikiType.MEDIAWIKI:
            wiki_infobox_source = wikienv.get_template("infobox.wiki").render(
                protocoltype=protocol.protocoltype)
            push_to_wiki(protocol, wiki_source, wiki_infobox_source,
                "Automatisch generiert vom Protokollsystem 3.0")
        elif wiki_type == WikiType.DOKUWIKI:
            push_to_dokuwiki(protocol, wiki_source,
                "Automatisch generiert vom Protokollsystem 3.0")
    protocol.done = True
    db.session.commit()

def push_to_wiki(protocol, content, infobox_content, summary):
    push_to_wiki_async.delay(protocol.id, content, infobox_content, summary)

@celery.task
def push_to_wiki_async(protocol_id, content, infobox_content, summary):
    with WikiClient() as wiki_client, app.app_context():
        protocol = Protocol.query.filter_by(id=protocol_id).first()
        try:
            wiki_client.edit_page(
                title=protocol.protocoltype.get_wiki_infobox_title(),
                content=infobox_content,
                summary=summary)
            wiki_client.edit_page(
                title=protocol.get_wiki_title(),
                content=content,
                summary=summary)
        except WikiException as exc:
            error = protocol.create_error("Pushing to Wiki", "Pushing to Wiki failed.", str(exc))
            db.session.add(error)
            db.session.commit()

def push_to_dokuwiki(protocol, content, summary):
    push_to_dokuwiki_async.delay(protocol.id, content, summary)

@celery.task
def push_to_dokuwiki_async(protocol_id, content, summary):
    protocol = Protocol.query.filter_by(id=protocol_id).first()
    with xmlrpc.client.ServerProxy(config.WIKI_API_URL) as proxy:
        if not proxy.wiki.putPage(protocol.get_wiki_title(),
            content, {"sum": "Automatisch generiert vom Protokollsystem 3."}):
            error = protocol.create_error("Pushing to Wiki",
                "Pushing to Wiki failed." "")
            db.session.add(error)
            db.session.commit()

def compile(content, protocol, show_private, maxdepth):
   compile_async.delay(content, protocol.id, show_private=show_private, maxdepth=maxdepth)

def compile_decision(content, decision, maxdepth):
    compile_async.delay(content, decision.id, use_decision=True, maxdepth=maxdepth)

@celery.task
def compile_async(content, protocol_id, show_private=False, use_decision=False, maxdepth=5):
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
            protocol_class_filename = "protokoll2.cls"
            log_filename = "protocol.log"
            with open(os.path.join(compile_dir, protocol_source_filename), "w") as source_file:
                source_file.write(content)
            protocol2_class_source = texenv.get_template(protocol_class_filename).render(fonts=config.FONTS, maxdepth=maxdepth, bulletpoints=config.LATEX_BULLETPOINTS)
            with open(os.path.join(compile_dir, protocol_class_filename), "w") as protocol2_class_file:
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
                document = Document(protocol_id=protocol.id,
                    name="protokoll{}_{}_{}.pdf".format(
                        "_intern" if show_private else "",
                        protocol.protocoltype.short_name,
                        date_filter_short(protocol.date)),
                    filename="",
                    is_compiled=True,
                    is_private=show_private)
            else:
                document = DecisionDocument(decision_id=decision.id,
                    name="beschluss_{}_{}_{}.pdf".format(
                        protocol.protocoltype.short_name,
                        date_filter_short(protocol.date),
                        decision.id),
                    filename="")
            db.session.add(document)
            db.session.commit()
            target_filename = "compiled-{}-{}.pdf".format(document.id, "internal" if show_private else "public")
            if use_decision:
                target_filename = "decision-{}-{}-{}.pdf".format(protocol.id, decision.id, document.id)
            document.filename = target_filename
            shutil.copy(os.path.join(compile_dir, protocol_target_filename), os.path.join(config.DOCUMENTS_PATH, target_filename))
            db.session.commit()
            shutil.copy(os.path.join(compile_dir, log_filename), "/tmp/proto-tex.log")
        except subprocess.SubprocessError:
            log = ""
            total_log_filename = os.path.join(compile_dir, log_filename)
            if os.path.isfile(total_log_filename):
                with open(total_log_filename, "r") as log_file:
                    log = "Log:\n\n" + add_line_numbers(log_file.read())
            else:
                log = "Logfile not found."
            total_source_filename = os.path.join(compile_dir, protocol_source_filename)
            if os.path.isfile(total_source_filename):
                with open(total_source_filename, "r") as source_file:
                    log += "\n\nSource:\n\n" + add_line_numbers(source_file.read())
            total_class_filename = os.path.join(compile_dir, protocol_class_filename)
            if os.path.isfile(total_class_filename):
                with open(total_class_filename, "r") as class_file:
                    log += "\n\nClass:\n\n" + add_line_numbers(class_file.read())
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
            db.session.add(error)
            db.session.commit()
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
            print("sending public reminder mail to {}".format(protocol.protocoltype.public_mail))
            send_mail(protocol, protocol.protocoltype.public_mail,
                "Tagesordnung der {}".format(protocol.protocoltype.name),
                reminder_text, reply_to=protocol.protocoltype.public_mail)
        if reminder.send_private:
            print("sending private reminder mail to {}".format(protocol.protocoltype.private_mail))
            send_mail(protocol, protocol.protocoltype.private_mail,
                "Tagesordnung der {}".format(protocol.protocoltype.name),
                reminder_text, reply_to=protocol.protocoltype.private_mail)

def remind_finishing(protocol, delay_days, min_delay_days):
    remind_finishing.delay(protocol.id, delay_days, min_delay_days)

@celery.task
def remind_finishing(protocol_id, delay_days, min_delay_days):
    with app.app_context():
        protocol = Protocol.query.filter_by(id=protocol_id).first()
        mail_text = render_template("remind-finishing-mail.txt",
            protocol=protocol, delay_days=delay_days,
            min_delay_days=min_delay_days)
        send_mail(protocol, protocol.protocoltype.private_mail,
            "Unfertiges Protokoll der {}".format(protocol.protocoltype.name),
            mail_text, reply_to=protocol.protocoltype.private_mail)

def send_protocol_private(protocol):
    send_protocol_async.delay(protocol.id, show_private=True)
    send_todomails_async.delay(protocol.id)

def send_protocol_public(protocol):
    send_protocol_async.delay(protocol.id, show_private=False)

@celery.task
def send_protocol_async(protocol_id, show_private):
    with app.app_context():
        protocol = Protocol.query.filter_by(id=protocol_id).first()
        next_protocol = Protocol.query.filter_by(protocoltype_id=protocol.protocoltype.id).filter_by(done=False).filter(Protocol.date > datetime.now()).order_by(Protocol.date).first()
        to_addr = protocol.protocoltype.private_mail if show_private else protocol.protocoltype.public_mail
        subject = "{}{}-Protokoll vom {}".format("Internes " if show_private else "", protocol.protocoltype.short_name, date_filter(protocol.date))
        mail_content = render_template("protocol-mail.txt", protocol=protocol, show_private=show_private, next_protocol=next_protocol)
        appendix = [(document.name, document.as_file_like())
            for document in protocol.documents
            if show_private or not document.is_private
        ]
        send_mail(protocol, to_addr, subject, mail_content, appendix)

@celery.task
def send_todomails_async(protocol_id):
    with app.app_context():
        protocol = Protocol.query.filter_by(id=protocol_id).first()
        all_todos = [
            todo for todo in Todo.query.all()
            if not todo.is_done()
            and todo.protocoltype == protocol.protocoltype
        ]
        users = {user for todo in all_todos for user in todo.get_users()}
        grouped_todos = {
            user: [todo for todo in all_todos if user in todo.get_users()]
            for user in users
        }
        subject = "Du hast noch was zu tun!"
        todomail_providers = getattr(config, "ADDITIONAL_TODOMAIL_PROVIDERS", None)
        additional_todomails = {}
        if todomail_providers:
            for provider in todomail_providers:
                todomail_dict = provider()
                for key in todomail_dict:
                    if key not in additional_todomails:
                        name, mail = todomail_dict[key]
                        additional_todomails[key] = TodoMail(name, mail)
        for user in users:
            todomail = TodoMail.query.filter(TodoMail.name.ilike(user)).first()
            if todomail is None:
                if user in additional_todomails:
                    todomail = additional_todomails[user]
            if todomail is None:
                error = protocol.create_error("Sending Todomail", "Sending Todomail failed.", "User {} has no Todo-Mail-Assignment.".format(user))
                db.session.add(error)
                db.session.commit()
                continue
            to_addr = todomail.get_formatted_mail()
            mail_content = render_template("todo-mail.txt", protocol=protocol, todomail=todomail, todos=grouped_todos[user])
            send_mail(protocol, to_addr, subject, mail_content,
                reply_to=protocol.protocoltype.private_mail)

def send_mail(protocol, to_addr, subject, content, appendix=None, reply_to=None):
    if to_addr is not None and len(to_addr.strip()) > 0:
        send_mail_async.delay(protocol.id, to_addr, subject, content, appendix, reply_to)

@celery.task
def send_mail_async(protocol_id, to_addr, subject, content, appendix, reply_to):
    with app.app_context():
        protocol = Protocol.query.filter_by(id=protocol_id).first()
        try:
            mail_manager.send(to_addr, subject, content, appendix, reply_to)
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

def set_etherpad_content(protocol):
    set_etherpad_content_async.delay(protocol.id)

@celery.task
def set_etherpad_content_async(protocol_id):
    with app.app_context():
        protocol = Protocol.query.filter_by(id=protocol_id).first()
        identifier = protocol.get_identifier()
        return set_etherpad_text(identifier, protocol.get_template())
    
