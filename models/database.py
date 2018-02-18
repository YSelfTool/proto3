from flask import render_template, send_file, url_for, redirect, flash, request

from datetime import datetime, time, date, timedelta
import math
from io import StringIO, BytesIO
from enum import Enum
from uuid import uuid4

from shared import db, date_filter, date_filter_short, escape_tex, DATE_KEY, START_TIME_KEY, END_TIME_KEY, current_user
from utils import random_string, get_etherpad_url, split_terms, check_ip_in_networks
from models.errors import DateNotMatchingException

import os

from sqlalchemy import event
from sqlalchemy.orm import relationship, backref, sessionmaker
from sqlalchemy.ext.hybrid import hybrid_method

import config
from todostates import make_states

class DatabaseModel(db.Model):
    __abstract__ = True

    def has_public_view_right(self, user):
        return self.get_parent().has_public_view_right(user)

    def has_private_view_right(self, user):
        return self.get_parent().has_private_view_right(user)

    def has_modify_right(self, user):
        return self.get_parent().has_modify_right(user)

    def has_publish_right(self, user):
        return self.get_parent().has_publish_right(user)

    def has_admin_right(self, user):
        return self.get_parent().has_admin_right(user)

    def __repr__(self):
        columns = []
        for column in self.__table__.columns:
            column_name = column.key
            value = getattr(self, column_name)
            if isinstance(value, str):
                value = "'" + value + "'"
            columns.append("{}={}".format(column_name, value))
        return "{}({})".format(self.__class__.__name__, ", ".join(columns))

class ProtocolType(DatabaseModel):
    __tablename__ = "protocoltypes"
    __model_name__ = "protocoltype"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String, unique=True)
    short_name = db.Column(db.String, unique=True)
    organization = db.Column(db.String)
    usual_time = db.Column(db.Time)
    is_public = db.Column(db.Boolean)
    modify_group = db.Column(db.String)
    private_group = db.Column(db.String)
    public_group = db.Column(db.String)
    publish_group = db.Column(db.String)
    private_mail = db.Column(db.String)
    public_mail = db.Column(db.String)
    non_reproducible_pad_links = db.Column(db.Boolean)
    use_wiki = db.Column(db.Boolean)
    wiki_category = db.Column(db.String)
    wiki_only_public = db.Column(db.Boolean)
    printer = db.Column(db.String)
    calendar = db.Column(db.String)
    restrict_networks = db.Column(db.Boolean)
    allowed_networks = db.Column(db.String)

    protocols = relationship("Protocol", backref=backref("protocoltype"), cascade="all, delete-orphan", order_by="Protocol.id")
    default_tops = relationship("DefaultTOP", backref=backref("protocoltype"), cascade="all, delete-orphan", order_by="DefaultTOP.number")
    reminders = relationship("MeetingReminder", backref=backref("protocoltype"), cascade="all, delete-orphan", order_by="MeetingReminder.days_before")
    todos = relationship("Todo", backref=backref("protocoltype"), order_by="Todo.id")
    metas = relationship("DefaultMeta", backref=backref("protocoltype"), cascade="all, delete-orphan")
    decisioncategories = relationship("DecisionCategory", backref=backref("protocoltype"), cascade="all, delete-orphan")

    def get_latest_protocol(self):
        candidates = sorted([protocol for protocol in self.protocols if protocol.is_done()], key=lambda p: p.date, reverse=True)
        if len(candidates) == 0:
            return None
        return candidates[0]

    def has_public_view_right(self, user, check_networks=True):
        return (self.has_public_anonymous_view_right(check_networks=check_networks)
            or (user is not None and self.has_public_authenticated_view_right(user))
            or self.has_admin_right(user))

    def has_public_anonymous_view_right(self, check_networks=True):
        return (self.is_public
            and ((not self.restrict_networks or not check_networks)
                or check_ip_in_networks(self.allowed_networks)))

    def has_public_authenticated_view_right(self, user):
        return ((self.public_group != "" and self.public_group in user.groups)
            or (self.private_group != "" and self.private_group in user.groups))

    def has_private_view_right(self, user):
        return ((user is not None
            and (self.private_group != "" and self.private_group in user.groups))
            or self.has_admin_right(user))

    def has_modify_right(self, user):
        return ((user is not None
            and (self.modify_group != "" and self.modify_group in user.groups))
            or self.has_admin_right(user))

    def has_publish_right(self, user):
        return ((user is not None
            and (self.publish_group != "" and self.publish_group in user.groups))
            or self.has_admin_right(user))

    def has_admin_right(self, user):
        return (user is not None and config.ADMIN_GROUP in user.groups)

    @staticmethod
    def get_modifiable_protocoltypes(user):
        return [
            protocoltype for protocoltype in ProtocolType.query.all()
            if protocoltype.has_modify_right(user)
        ]

    @staticmethod
    def get_public_protocoltypes(user, check_networks=True):
        return [
            protocoltype for protocoltype in ProtocolType.query.all()
            if protocoltype.has_public_view_right(user, check_networks=check_networks)
        ]

    @staticmethod
    def get_private_protocoltypes(user):
        return [
            protocoltype for protocoltype in ProtocolType.query.all()
            if protocoltype.has_private_view_right(user)
        ]

    def get_wiki_infobox(self):
        return "Infobox {}".format(self.short_name)

    def get_wiki_infobox_title(self):
        return "Vorlage:{}".format(self.get_wiki_infobox())


class Protocol(DatabaseModel):
    __tablename__ = "protocols"
    __model_name__ = "protocol"
    id = db.Column(db.Integer, primary_key=True)
    protocoltype_id = db.Column(db.Integer, db.ForeignKey("protocoltypes.id"))
    source = db.Column(db.String)
    content_public = db.Column(db.String)
    content_private = db.Column(db.String)
    content_html_public = db.Column(db.String)
    content_html_private = db.Column(db.String)
    date = db.Column(db.Date)
    start_time = db.Column(db.Time)
    end_time = db.Column(db.Time)
    done = db.Column(db.Boolean, nullable=False, default=False)
    public = db.Column(db.Boolean)
    pad_identifier = db.Column(db.String)

    tops = relationship("TOP", backref=backref("protocol"), cascade="all, delete-orphan", order_by="TOP.number")
    decisions = relationship("Decision", backref=backref("protocol"), cascade="all, delete-orphan", order_by="Decision.id")
    documents = relationship("Document", backref=backref("protocol"), cascade="all, delete-orphan", order_by="Document.is_compiled")
    errors = relationship("Error", backref=backref("protocol"), cascade="all, delete-orphan", order_by="Error.id")
    metas = relationship("Meta", backref=backref("protocol"), cascade="all, delete-orphan")
    localtops = relationship("LocalTOP", backref=backref("protocol"), cascade="all, delete-orphan")

    likes = relationship("Like", secondary="likeprotocolassociations")

    def get_parent(self):
        return self.protocoltype

    def create_error(self, action, name, description):
        now = datetime.now()
        return Error(protocol_id=self.id, action=action, name=name,
            datetime=now, description=description)

    def create_localtops(self):
        local_tops = []
        for default_top in self.protocoltype.default_tops:
            local_tops.append(LocalTOP(defaulttop_id=default_top.id,
                protocol_id=self.id, description=default_top.description or ""))
        return local_tops

    def fill_from_remarks(self, remarks):
        def _date_or_lazy(key, get_date=False, get_time=False):
            formats = []
            if get_date:
                formats.append("%d.%m.%Y")
            if get_time:
                formats.append("%H:%M")
            format = " ".join(formats)
            try:
                date = datetime.strptime(remarks[key].value.strip(), format)
                if (get_time and get_date) or (not get_time and not get_date):
                    return date
                elif get_time:
                    return date.time()
                elif get_date:
                    return date.date()
            except ValueError as exc:
                if config.PARSER_LAZY:
                    return None
                raise exc
        if DATE_KEY in remarks:
            new_date = _date_or_lazy(DATE_KEY, get_date=True)
            if self.date is not None:
                if new_date != self.date:
                    raise DateNotMatchingException(original_date=self.date, protocol_date=new_date)
            else:
                self.date = new_date
        if START_TIME_KEY in remarks:
            self.start_time = _date_or_lazy(START_TIME_KEY, get_time=True)
        if END_TIME_KEY in remarks:
            self.end_time = _date_or_lazy(END_TIME_KEY, get_time=True)
        old_metas = list(self.metas)
        for meta in old_metas:
            db.session.delete(meta)
        db.session.commit()
        for default_meta in self.protocoltype.metas:
            if default_meta.key in remarks:
                value = remarks[default_meta.key].value.strip()
                meta = Meta(protocol_id=self.id, name=default_meta.name, value=value, internal=default_meta.internal)
                db.session.add(meta)
        db.session.commit()

    def has_public_view_right(self, user):
        return (
            (self.public and self.protocoltype.has_public_view_right(user))
            or self.protocoltype.has_private_view_right(user)
        )

    def is_done(self):
        return self.done

    def get_identifier(self):
        if self.pad_identifier is not None:
            return self.pad_identifier
        if self.date is None:
            return None
        return self.get_short_identifier()

    def get_short_identifier(self):
        return "{}-{}".format(
            self.protocoltype.short_name.lower(),
            self.date.strftime("%y-%m-%d"))

    def get_wiki_title(self):
        return "Protokoll:{}-{:%Y-%m-%d}".format(self.protocoltype.short_name, self.date)

    def get_etherpad_link(self):
        if self.pad_identifier is None:
            identifier = self.get_identifier()
            if self.protocoltype.non_reproducible_pad_links:
                identifier = "{}-{}".format(identifier, str(uuid4()).replace("-", ""))[:50]
            self.pad_identifier = identifier
            db.session.commit()
        return get_etherpad_url(self.pad_identifier)

    def get_time(self):
        if self.start_time is not None:
            return self.start_time
        return self.protocoltype.usual_time

    def get_datetime(self):
        time = self.get_time()
        return datetime(self.date.year, self.date.month, self.date.day, time.hour, time.minute)

    def has_nonplanned_tops(self):
        return len([top for top in self.tops if not top.planned]) > 0

    def get_originating_todos(self):
        return [todo for todo in self.todos if self == todo.get_first_protocol()]

    def get_open_todos(self):
        return [
            todo for todo in self.protocoltype.todos
            if not todo.is_done()
        ]

    def has_compiled_document(self, private=None):
        candidates = [
            document for document in self.documents
            if document.is_compiled
                and (private is None or document.is_private == private)
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

    def get_tops(self):
        tops_before, tops_after = [], []
        if not self.has_nonplanned_tops():
            for default_top in self.protocoltype.default_tops:
                top = default_top.get_top(self)
                if default_top.is_at_end():
                    tops_after.append(top)
                else:
                    tops_before.append(top)
        return tops_before + self.tops + tops_after

    @staticmethod
    def create_new_protocol(protocoltype, date, start_time=None):
        if start_time is None:
            start_time = protocoltype.usual_time
        protocol = Protocol(protocoltype_id=protocoltype.id,
            date=date, start_time=start_time)
        db.session.add(protocol)
        db.session.commit()
        for local_top in protocol.create_localtops():
            db.session.add(local_top)
        for default_meta in protocoltype.metas:
            if default_meta.prior:
                meta = Meta(protocol_id=protocol.id, name=default_meta.name,
                    internal=default_meta.internal, value=default_meta.value)
                db.session.add(meta)
        db.session.commit()
        import tasks
        tasks.push_tops_to_calendar(protocol)
        return protocol

        

@event.listens_for(Protocol, "before_delete")
def on_protocol_delete(mapper, connection, protocol):
    protocol.delete_orphan_todos()


class DefaultTOP(DatabaseModel):
    __tablename__ = "defaulttops"
    __model_name__ = "defaulttop"
    id = db.Column(db.Integer, primary_key=True)
    protocoltype_id = db.Column(db.Integer, db.ForeignKey("protocoltypes.id"))
    name = db.Column(db.String)
    number = db.Column(db.Integer)
    description = db.Column(db.String)

    localtops = relationship("LocalTOP", backref=backref("defaulttop"), cascade="all, delete-orphan")

    def get_parent(self):
        return self.protocoltype

    def is_at_end(self):
        return self.number > 0

    def get_localtop(self, protocol):
        return LocalTOP.query.filter_by(defaulttop_id=self.id,
            protocol_id=protocol.id).first()

    def get_top(self, protocol):
        localtop = self.get_localtop(protocol)
        top = TOP(protocol_id=protocol.id, name=self.name,
            description=localtop.description)
        return top

class TOP(DatabaseModel):
    __tablename__ = "tops"
    __model_name__ = "top"
    id = db.Column(db.Integer, primary_key=True)
    protocol_id = db.Column(db.Integer, db.ForeignKey("protocols.id"))
    name = db.Column(db.String)
    number = db.Column(db.Integer)
    planned = db.Column(db.Boolean)
    description = db.Column(db.String)

    likes = relationship("Like", secondary="liketopassociations")

    def get_parent(self):
        return self.protocol

class LocalTOP(DatabaseModel):
    __tablename__ = "localtops"
    __model_name__ = "localtop"
    id = db.Column(db.Integer, primary_key=True)
    protocol_id = db.Column(db.Integer, db.ForeignKey("protocols.id"))
    defaulttop_id = db.Column(db.Integer, db.ForeignKey("defaulttops.id"))
    description = db.Column(db.String)

    def get_parent(self):
        return self.protocol

    def is_expandable(self):
        user = current_user()
        return (self.has_private_view_right(user)
            and self.description is not None
            and len(self.description) > 0)

    def get_css_classes(self):
        classes = ["defaulttop"]
        if self.is_expandable():
            classes.append("expansion-button")
        return classes

class Document(DatabaseModel):
    __tablename__ = "documents"
    __model_name__ = "document"
    id = db.Column(db.Integer, primary_key=True)
    protocol_id = db.Column(db.Integer, db.ForeignKey("protocols.id"))
    name = db.Column(db.String)
    filename = db.Column(db.String)
    is_compiled = db.Column(db.Boolean)
    is_private = db.Column(db.Boolean)

    def get_parent(self):
        return self.protocol

    def get_filename(self):
        return os.path.join(config.DOCUMENTS_PATH, self.filename)

    def as_file_like(self):
        with open(self.get_filename(), "rb") as file:
            return BytesIO(file.read())

@event.listens_for(Document, "before_delete")
def on_document_delete(mapper, connection, document):
    if document.filename is not None:
        document_path = document.get_filename()
        if os.path.isfile(document_path):
            os.remove(document_path)

class DecisionDocument(DatabaseModel):
    __tablename__ = "decisiondocuments"
    __model_name__ = "decisiondocument"
    id = db.Column(db.Integer, primary_key=True)
    decision_id = db.Column(db.Integer, db.ForeignKey("decisions.id"))
    name = db.Column(db.String)
    filename = db.Column(db.String)

    def get_parent(self):
        return self.decision

    def get_filename(self):
        return os.path.join(config.DOCUMENTS_PATH, self.filename)

    def as_file_like(self):
        with open(self.get_filename(), "rb") as file:
            return BytesIO(file.read())

@event.listens_for(DecisionDocument, "before_delete")
def on_decisions_document_delete(mapper, connection, document):
    if document.filename is not None:
        document_path = document.get_filename()
        if os.path.isfile(document_path):
            os.remove(document_path)

class TodoState(Enum):
    open = 0
    waiting = 1
    in_progress = 2
    after = 3
    before = 4
    orphan = 5
    done = 6
    rejected = 7
    obsolete = 8

    def get_name(self):
        STATE_TO_NAME, NAME_TO_STATE = make_states(TodoState)
        return STATE_TO_NAME[self]
    
    @staticmethod
    def get_name_to_state():
        STATE_TO_NAME, NAME_TO_STATE = make_states(TodoState)
        return NAME_TO_STATE

    @staticmethod
    def get_state_to_name():
        STATE_TO_NAME, NAME_TO_STATE = make_states(TodoState)
        return STATE_TO_NAME

    def needs_date(self):
        return self in [TodoState.after, TodoState.before]

    def is_done(self):
        return self in [TodoState.done, TodoState.rejected, TodoState.obsolete]

    @staticmethod
    def from_name(name):
        name = name.strip().lower()
        STATE_TO_NAME, NAME_TO_STATE = make_states(TodoState)
        if name not in NAME_TO_STATE:
            raise ValueError("Unknown state: '{}'".format(name))
        return NAME_TO_STATE[name]

    @staticmethod
    def from_name_lazy(name):
        name = name.strip().lower()
        STATE_TO_NAME, NAME_TO_STATE = make_states(TodoState)
        for key in NAME_TO_STATE:
            if name.startswith(key):
                return NAME_TO_STATE[key]
        raise ValueError("{} does not start with a state.".format(name))

    @staticmethod
    def from_name_with_date(name, protocol=None):
        name = name.strip().lower()
        if not " " in name:
            raise ValueError("{} does definitely not contain a state and a date".format(name))
        name_part, date_part = name.split(" ", 1)
        state = TodoState.from_name(name_part)
        date = None
        last_exc = None
        formats = [("%d.%m.%Y", False)]
        if config.PARSER_LAZY:
            formats.extend([("%d.%m.", True), ("%d.%m", True)])
        for format, year_missing in formats:
            try:
                date = datetime.strptime(date_part.strip(), format).date()
                if year_missing:
                    year = datetime.now().year
                    if protocol is not None:
                        year = protocol.date.year
                    date = datetime(year=year, month=date.month, day=date.day).date()
                break
            except ValueError as exc:
                last_exc = exc
                continue
        if date is None:
            raise last_exc
        return state, date


class Todo(DatabaseModel):
    __tablename__ = "todos"
    __model_name__ = "todo"
    id = db.Column(db.Integer, primary_key=True)
    protocoltype_id = db.Column(db.Integer, db.ForeignKey("protocoltypes.id"))
    number = db.Column(db.Integer)
    who = db.Column(db.String)
    description = db.Column(db.String)
    state = db.Column(db.Enum(TodoState), nullable=False)
    date = db.Column(db.Date, nullable=True)

    protocols = relationship("Protocol", secondary="todoprotocolassociations", backref="todos")
    likes = relationship("Like", secondary="liketodoassociations")

    def get_parent(self):
        return self.protocoltype

    def is_done(self):
        if self.state.needs_date():
            if self.state == TodoState.after:
                return datetime.now().date() <= self.date
            elif self.state == TodoState.before:
                return datetime.now().date() >= self.date
        return self.state.is_done()

    def get_id(self):
        return self.number if self.number is not None else self.id

    def get_first_protocol(self):
        candidates = sorted(self.protocols, key=lambda p: p.date)
        if len(candidates) == 0:
            return None
        return candidates[0]

    def get_users(self):
        return [
            user.lower().strip()
            for user in split_terms(self.who, separators=" ,\t")
        ]

    def get_state(self):
        return "[{}]".format(self.get_state_plain())
    def get_state_plain(self):
        result = self.state.get_name()
        if self.state.needs_date():
            result = "{} {}".format(result, date_filter_short(self.date))
        return result
    def get_state_tex(self):
        return self.get_state_plain()

    def is_new(self, current_protocol=None):
        if current_protocol is not None:
            return self.get_first_protocol() == current_protocol
        return len(self.protocols) == 1

    def render_html(self, current_protocol=None):
        parts = [
            self.get_state(),
            "<strong>{}:</strong>".format(self.who),
            self.description
        ]
        return " ".join(parts)

    def render_latex(self, current_protocol=None):
        return r"\Todo{{{}}}{{{}}}{{{}}}{{{}}}".format(
            "Neuer Todo" if self.is_new(current_protocol) else "Todo",
            escape_tex(self.who),
            escape_tex(self.description),
            escape_tex(self.get_state_tex())
        )

    def render_wikitext(self, current_protocol=None, use_dokuwiki=False):
        bold = "'''"
        if use_dokuwiki:
            bold = "**"
        return "{0}{1}:{0} {2}: {3} - {4}".format(bold,
            "Neuer Todo" if self.is_new(current_protocol) else "Todo",
            self.who,
            self.description,
            self.get_state_plain()
        )

    def render_template(self):
        parts = ["todo", self.who, self.description, self.state.get_name()]
        if self.state.needs_date():
            parts.append(date_filter_short(self.date))
        parts.append("id {}".format(self.get_id()))
        return "[{}]".format(";".join(parts))

class TodoProtocolAssociation(DatabaseModel):
    __tablename__ = "todoprotocolassociations"
    todo_id = db.Column(db.Integer, db.ForeignKey("todos.id"), primary_key=True)
    protocol_id = db.Column(db.Integer, db.ForeignKey("protocols.id"), primary_key=True)

class Decision(DatabaseModel):
    __tablename__ = "decisions"
    __model_name__ = "decision"
    id = db.Column(db.Integer, primary_key=True)
    protocol_id = db.Column(db.Integer, db.ForeignKey("protocols.id"))
    content = db.Column(db.String)

    document = relationship("DecisionDocument", backref=backref("decision"), cascade="all, delete-orphan", uselist=False)

    categories = relationship("DecisionCategory", secondary="decisioncategoryassociations")
    likes = relationship("Like", secondary="likedecisionassociations")

    def get_parent(self):
        return self.protocol

    def get_categories_str(self):
        return ", ".join(map(lambda c: c.name, self.categories))

class DecisionCategory(DatabaseModel):
    __tablename__ = "decisioncategories"
    __model_name__ = "decisioncategory"
    id = db.Column(db.Integer, primary_key=True)
    protocoltype_id = db.Column(db.Integer, db.ForeignKey("protocoltypes.id"))
    name = db.Column(db.String)

    def get_parent(self):
        return self.protocoltype

class DecisionCategoryAssociation(DatabaseModel):
    __tablename__ = "decisioncategoryassociations"
    decision_id = db.Column(db.Integer, db.ForeignKey("decisions.id"), primary_key=True)
    decisioncategory_id = db.Column(db.Integer, db.ForeignKey("decisioncategories.id"), primary_key=True)

class MeetingReminder(DatabaseModel):
    __tablename__ = "meetingreminders"
    __model_name__ = "meetingreminder"
    id = db.Column(db.Integer, primary_key=True)
    protocoltype_id = db.Column(db.Integer, db.ForeignKey("protocoltypes.id"))
    days_before = db.Column(db.Integer)
    send_public = db.Column(db.Boolean)
    send_private = db.Column(db.Boolean)
    additional_text = db.Column(db.String)

    def get_parent(self):
        return self.protocoltype

class Error(DatabaseModel):
    __tablename__ = "errors"
    __model_name__ = "error"
    id = db.Column(db.Integer, primary_key=True)
    protocol_id = db.Column(db.Integer, db.ForeignKey("protocols.id"))
    action = db.Column(db.String)
    name = db.Column(db.String)
    datetime = db.Column(db.DateTime)
    description = db.Column(db.String)

    def get_parent(self):
        return self.protocol

    def get_short_description(self):
        if not self.description:
            return ""
        lines = self.description.splitlines()
        if len(lines) <= 4:
            return "\n".join(lines)
        return "\n".join(["\n".join(lines[:2]), "…", "\n".join(lines[-2:])])

class TodoMail(DatabaseModel):
    __tablename__ = "todomails"
    __model_name__ = "todomail"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String, unique=True)
    mail = db.Column(db.String)

    def get_formatted_mail(self):
        return "{} <{}>".format(self.name, self.mail)

class OldTodo(DatabaseModel):
    __tablename__ = "oldtodos"
    __model_name__ = "oldtodo"
    id = db.Column(db.Integer, primary_key=True)
    old_id = db.Column(db.Integer)
    who = db.Column(db.String)
    description = db.Column(db.String)
    protocol_key = db.Column(db.String)

class DefaultMeta(DatabaseModel):
    __tablename__ = "defaultmetas"
    __model_name__ = "defaultmeta"
    id = db.Column(db.Integer, primary_key=True)
    protocoltype_id = db.Column(db.Integer, db.ForeignKey("protocoltypes.id"))
    key = db.Column(db.String)
    name = db.Column(db.String)
    value = db.Column(db.String)
    internal = db.Column(db.Boolean)
    prior = db.Column(db.Boolean, default=False, nullable=False)

    def get_parent(self):
        return self.protocoltype

class Meta(DatabaseModel):
    __tablename__ = "metas"
    __model_name__ = "meta"
    id = db.Column(db.Integer, primary_key=True)
    protocol_id = db.Column(db.Integer, db.ForeignKey("protocols.id"))
    name = db.Column(db.String)
    value = db.Column(db.String)
    internal = db.Column(db.Boolean)

    def get_parent(self):
        return self.protocol

class Like(DatabaseModel):
    __tablename__ = "likes"
    __model_name__ = "like"
    id = db.Column(db.Integer, primary_key=True)
    who = db.Column(db.String)

class LikeProtocolAssociation(DatabaseModel):
    __tablename__ = "likeprotocolassociations"
    like_id = db.Column(db.Integer, db.ForeignKey("likes.id"), primary_key=True)
    protocol_id = db.Column(db.Integer, db.ForeignKey("protocols.id"), primary_key=True)

class LikeTodoAssociation(DatabaseModel):
    __tablename__ = "liketodoassociations"
    like_id = db.Column(db.Integer, db.ForeignKey("likes.id"), primary_key=True)
    todo_id = db.Column(db.Integer, db.ForeignKey("todos.id"), primary_key=True)

class LikeDecisionAssociation(DatabaseModel):
    __tablename__ = "likedecisionassociations"
    like_id = db.Column(db.Integer, db.ForeignKey("likes.id"), primary_key=True)
    decision_id = db.Column(db.Integer, db.ForeignKey("decisions.id"), primary_key=True)

class LikeTOPAssociation(DatabaseModel):
    __tablename__ = "liketopassociations"
    like_id = db.Column(db.Integer, db.ForeignKey("likes.id"), primary_key=True)
    top_id = db.Column(db.Integer, db.ForeignKey("tops.id"), primary_key=True)


ALL_MODELS = [
    ProtocolType, Protocol, DefaultTOP, TOP, Document, DecisionDocument,
    Todo, Decision, MeetingReminder, Error, DefaultMeta, Meta, DecisionCategory
]
