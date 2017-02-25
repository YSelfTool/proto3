from flask import render_template, send_file, url_for, redirect, flash, request

from datetime import datetime, time, date, timedelta
import math

from shared import db
from utils import random_string, url_manager, get_etherpad_url
from models.errors import DateNotMatchingException

import os

from sqlalchemy import event
from sqlalchemy.orm import relationship, backref, sessionmaker
from sqlalchemy.ext.hybrid import hybrid_method

import config

class ProtocolType(db.Model):
    __tablename__ = "protocoltypes"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String, unique=True)
    short_name = db.Column(db.String, unique=True)
    organization = db.Column(db.String)
    is_public = db.Column(db.Boolean)
    private_group = db.Column(db.String)
    public_group = db.Column(db.String)
    private_mail = db.Column(db.String)
    public_mail = db.Column(db.String)
    use_wiki = db.Column(db.Boolean)
    wiki_category = db.Column(db.String)
    wiki_only_public = db.Column(db.Boolean)
    printer = db.Column(db.String)

    protocols = relationship("Protocol", backref=backref("protocoltype"), cascade="all, delete-orphan", order_by="Protocol.id")
    default_tops = relationship("DefaultTOP", backref=backref("protocoltype"), cascade="all, delete-orphan", order_by="DefaultTOP.number")
    reminders = relationship("MeetingReminder", backref=backref("protocoltype"), cascade="all, delete-orphan", order_by="MeetingReminder.days_before")
    todos = relationship("Todo", backref=backref("protocoltype"), order_by="Todo.id")

    def __init__(self, name, short_name, organization,
            is_public, private_group, public_group, private_mail, public_mail,
            use_wiki, wiki_category, wiki_only_public, printer):
        self.name = name
        self.short_name = short_name
        self.organization = organization
        self.is_public = is_public
        self.private_group = private_group
        self.public_group = public_group
        self.private_mail = private_mail
        self.public_mail = public_mail
        self.use_wiki = use_wiki
        self.wiki_category = wiki_category
        self.wiki_only_public = wiki_only_public
        self.printer = printer

    def __repr__(self):
        return ("<ProtocolType(id={}, short_name={}, name={}, "
                "organization={}, is_public={}, private_group={}, "
                "public_group={}, use_wiki={}, wiki_category='{}', "
                "wiki_only_public={}, printer={})>".format(
            self.id, self.short_name, self.name,
            self.organization, self.is_public, self.private_group,
            self.public_group, self.use_wiki, self.wiki_category,
            self.wiki_only_public, self.printer))

    def get_latest_protocol(self):
        candidates = sorted([protocol for protocol in self.protocols if protocol.is_done()], key=lambda p: p.date, reverse=True)
        if len(candidates) == 0:
            return None
        return candidates[0]

    @hybrid_method
    def has_public_view_right(self, user):
        return (self.is_public
            or (user is not None and 
                ((self.public_group != "" and self.public_group in user.groups)
                or (self.private_group != "" and self.private_group in user.groups))))

    def has_private_view_right(self, user):
        return (user is not None and self.private_group != "" and self.private_group in user.groups)

    def has_modify_right(self, user):
        return self.has_private_view_right(user)

    @staticmethod
    def get_modifiable_protocoltypes(user):
        return [
            protocoltype for protocoltype in ProtocolType.query.all()
            if protocoltype.has_modify_right(user)
        ]

    @staticmethod
    def get_public_protocoltypes(user):
        return [
            protocoltype for protocoltype in ProtocolType.query.all()
            if protocoltype.has_public_view_right(user)
        ]

    @staticmethod
    def get_private_protocoltypes(user):
        return [
            protocoltype for protocoltype in ProtocolType.query.all()
            if protocoltype.has_private_view_right(user)
        ]



class Protocol(db.Model):
    __tablename__ = "protocols"
    id = db.Column(db.Integer, primary_key=True)
    protocoltype_id = db.Column(db.Integer, db.ForeignKey("protocoltypes.id"))
    source = db.Column(db.String)
    content_public = db.Column(db.String)
    content_private = db.Column(db.String)
    date = db.Column(db.Date)
    start_time = db.Column(db.Time)
    end_time = db.Column(db.Time)
    author = db.Column(db.String)
    participants = db.Column(db.String)
    location = db.Column(db.String)
    done = db.Column(db.Boolean)

    tops = relationship("TOP", backref=backref("protocol"), cascade="all, delete-orphan", order_by="TOP.number")
    decisions = relationship("Decision", backref=backref("protocol"), cascade="all, delete-orphan", order_by="Decision.id")
    documents = relationship("Document", backref=backref("protocol"), cascade="all, delete-orphan", order_by="Document.is_compiled")
    errors = relationship("Error", backref=backref("protocol"), cascade="all, delete-orphan", order_by="Error.id")

    def __init__(self, protocoltype_id, date, source=None, content_public=None, content_private=None, start_time=None, end_time=None, author=None, participants=None, location=None, done=False):
        self.protocoltype_id = protocoltype_id
        self.date = date
        self.source = source
        self.content_private = content_private
        self.content_public = content_public
        self.start_time = start_time
        self.end_time = end_time
        self.author = author
        self.participants = participants
        self.location = location
        self.done = done

    def __repr__(self):
        return "<Protocol(id={}, protocoltype_id={})>".format(
            self.id, self.protocoltype_id)

    def create_error(self, action, name, description):
        now = datetime.now()
        return Error(self.id, action, name, now, description)

    def fill_from_remarks(self, remarks):
        new_date = datetime.strptime(remarks["Datum"].value.strip(), "%d.%m.%Y").date()
        if self.date is not None:
            if new_date != self.date:
                raise DateNotMatchingException(original_date=self.date, protocol_date=new_date)
        else:
            self.date = new_date
        self.start_time = datetime.strptime(remarks["Beginn"].value.strip(), "%H:%M").time()
        self.end_time = datetime.strptime(remarks["Ende"].value.strip(), "%H:%M").time()
        self.author = remarks["Autor"].value.strip()
        self.participants = remarks["Anwesende"].value.strip()
        self.location = remarks["Ort"].value.strip()

    def is_done(self):
        return self.done

    def get_identifier(self):
        if self.date is None:
            return None
        return "{}-{}".format(
            self.protocoltype.short_name.lower(),
            self.date.strftime("%y-%m-%d"))

    def get_wiki_title(self):
        return "Protokoll:{}-{:%Y-%m-%d}".format(self.protocoltype.short_name, self.date)

    def get_etherpad_link(self):
        identifier = self.get_identifier()
        if identifier is None:
            return ""
        return get_etherpad_url(self.get_identifier())

    def has_nonplanned_tops(self):
        return len([top for top in self.tops if not top.planned]) > 0

    def get_originating_todos(self):
        return [todo for todo in self.todos if self == todo.get_first_protocol()]

    def has_compiled_document(self):
        candidates = [
            document for document in self.documents
            if document.is_compiled
        ]
        return len(candidates) > 0

    def get_compiled_document(self, private=None):
        candidates = [
            document for document in self.documents
            if document.is_compiled
               and (private is None or document.is_private == private) 
        ]
        private_candidates = [document for document in candidates if document.is_private]
        public_candidates = [document for document in candidates if not document.is_private]
        if len(private_candidates) > 0:
            return private_candidates[0]
        elif len(public_candidates) > 0:
            return public_candidates[0]
        return None

    def get_template(self):
        return render_template("protocol-template.txt", protocol=self)

    def delete_orphan_todos(self):
        orphan_todos = [
            todo for todo in self.todos
            if len(todo.protocols) <= 1
        ]
        for todo in orphan_todos:
            self.todos.remove(todo)
            db.session.delete(todo)

@event.listens_for(Protocol, "before_delete")
def on_protocol_delete(mapper, connection, protocol):
    protocol.delete_orphan_todos()


class DefaultTOP(db.Model):
    __tablename__ = "defaulttops"
    id = db.Column(db.Integer, primary_key=True)
    protocoltype_id = db.Column(db.Integer, db.ForeignKey("protocoltypes.id"))
    name = db.Column(db.String)
    number = db.Column(db.Integer)

    def __init__(self, protocoltype_id, name, number):
        self.protocoltype_id = protocoltype_id
        self.name = name
        self.number = number

    def __repr__(self):
        return "<DefaultTOP(id={}, protocoltype_id={}, name={}, number={})>".format(
            self.id, self.protocoltype_id, self.name, self.number)

    def is_at_end(self):
        return self.number > 0

class TOP(db.Model):
    __tablename__ = "tops"
    id = db.Column(db.Integer, primary_key=True)
    protocol_id = db.Column(db.Integer, db.ForeignKey("protocols.id"))
    name = db.Column(db.String)
    number = db.Column(db.Integer)
    planned = db.Column(db.Boolean)

    def __init__(self, protocol_id, name, number, planned):
        self.protocol_id = protocol_id
        self.name = name
        self.number = number
        self.planned = planned

    def __repr__(self):
        return "<TOP(id={}, protocol_id={}, name={}, number={}, planned={})>".format(
            self.id, self.protocol_id, self.name, self.number, self.planned)

class Document(db.Model):
    __tablename__ = "documents"
    id = db.Column(db.Integer, primary_key=True)
    protocol_id = db.Column(db.Integer, db.ForeignKey("protocols.id"))
    name = db.Column(db.String)
    filename = db.Column(db.String)
    is_compiled = db.Column(db.Boolean)
    is_private = db.Column(db.Boolean)

    def __init__(self, protocol_id, name, filename, is_compiled, is_private):
        self.protocol_id = protocol_id
        self.name = name
        self.filename = filename
        self.is_compiled = is_compiled
        self.is_private = is_private

    def __repr__(self):
        return "<Document(id={}, protocol_id={}, name={}, filename={}, is_compiled={}, is_private={})>".format(
            self.id, self.protocol_id, self.name, self.filename, self.is_compiled, self.is_private)

    def get_filename(self):
        return os.path.join(config.DOCUMENTS_PATH, self.filename)

@event.listens_for(Document, "before_delete")
def on_document_delete(mapper, connection, document):
    if document.filename is not None:
        document_path = os.path.join(config.DOCUMENTS_PATH, document.filename)
        if os.path.isfile(document_path):
            os.remove(document_path)

class Todo(db.Model):
    __tablename__ = "todos"
    id = db.Column(db.Integer, primary_key=True)
    protocoltype_id = db.Column(db.Integer, db.ForeignKey("protocoltypes.id"))
    number = db.Column(db.Integer)
    who = db.Column(db.String)
    description = db.Column(db.String)
    tags = db.Column(db.String)
    done = db.Column(db.Boolean)

    protocols = relationship("Protocol", secondary="todoprotocolassociations", backref="todos")

    def __init__(self, type_id, who, description, tags, done, number=None):
        self.protocoltype_id = type_id
        self.who = who
        self.description = description
        self.tags = tags
        self.done = done
        self.number = number

    def __repr__(self):
        return "<Todo(id={}, number={}, who={}, description={}, tags={}, done={})>".format(
            self.id, self.number, self.who, self.description, self.tags, self.done)

    def get_id(self):
        return self.number if self.number is not None else self.id

    def get_first_protocol(self):
        candidates = sorted(self.protocols, key=lambda p: p.date)
        if len(candidates) == 0:
            return None
        return candidates[0]

    def get_state(self):
        return "[Erledigt]" if self.done else "[Offen]"
    def get_state_plain(self):
        return "Erledigt" if self.done else "Aktiv"
    def get_state_tex(self):
        return self.get_state_plain()

    def is_new(self, current_protocol=None):
        if current_protocol is not None:
            return self.get_first_protocol() == current_protocol
        return len(self.protocols) == 1

    def render_html(self):
        parts = [
            self.get_state(),
            "<strong>{}:</strong>".format(self.who),
            self.description
        ]
        return " ".join(parts)

    def render_latex(self, current_protocol=None):
        return r"\textbf{{{}}}: {}: {} -- {}".format(
            "Neuer Todo" if self.is_new(current_protocol) else "Todo",
            self.who,
            self.description,
            self.get_state_tex()
        )

    def render_wikitext(self, current_protocol=None):
        return "'''{}:''' {}: {} - {}".format(
            "Neuer Todo" if self.is_new(current_protocol) else "Todo",
            self.who,
            self.description,
            self.get_state_plain()
        )



class TodoProtocolAssociation(db.Model):
    __tablename__ = "todoprotocolassociations"
    todo_id = db.Column(db.Integer, db.ForeignKey("todos.id"), primary_key=True)
    protocol_id = db.Column(db.Integer, db.ForeignKey("protocols.id"), primary_key=True)

class Decision(db.Model):
    __tablename__ = "decisions"
    id = db.Column(db.Integer, primary_key=True)
    protocol_id = db.Column(db.Integer, db.ForeignKey("protocols.id"))
    content = db.Column(db.String)

    def __init__(self, protocol_id, content):
        self.protocol_id = protocol_id
        self.content = content

    def __repr__(self):
        return "<Decision(id={}, protocol_id={}, content='{}')>".format(
            self.id, self.protocol_id, self.content)

class MeetingReminder(db.Model):
    __tablename__ = "meetingreminders"
    id = db.Column(db.Integer, primary_key=True)
    protocoltype_id = db.Column(db.Integer, db.ForeignKey("protocoltypes.id"))
    days_before = db.Column(db.Integer)
    send_public = db.Column(db.Boolean)
    send_private = db.Column(db.Boolean)

    def __init__(self, protocoltype_id, days_before, send_public, send_private):
        self.protocoltype_id = protocoltype_id
        self.days_before = days_before
        self.send_public = send_public
        self.send_private = send_private

    def __repr__(self):
        return "<MeetingReminder(id={}, protocoltype_id={}, days_before={}, send_public={}, send_private={})>".format(
            self.id, self.protocoltype_id, self.days_before, self.send_public, self.send_private)

class Error(db.Model):
    __tablename__ = "errors"
    id = db.Column(db.Integer, primary_key=True)
    protocol_id = db.Column(db.Integer, db.ForeignKey("protocols.id"))
    action = db.Column(db.String)
    name = db.Column(db.String)
    datetime = db.Column(db.DateTime)
    description = db.Column(db.String)

    def __init__(self, protocol_id, action, name, datetime, description):
        self.protocol_id = protocol_id
        self.action = action
        self.name = name
        self.datetime = datetime
        self.description = description

    def __repr__(self):
        return "<Error(id={}, protocol_id={}, action={}, name={}, datetime={})>".format(
            self.id, self.protocol_id, self.action, self.name, self.datetime)
