from flask import render_template, send_file, url_for, redirect, flash, request

from datetime import datetime, date, timedelta
import time
import math

from shared import db
from utils import random_string, url_manager

#from models.tables import TexResponsiblesTable, TexSupportersTable

from sqlalchemy.orm import relationship, backref

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

    protocols = relationship("Protocol", backref=backref("protocoltype"), cascade="all, delete-orphan", order_by="Protocol.id")
    default_tops = relationship("DefaultTOP", backref=backref("protocoltype"), cascade="all, delete-orphan", order_by="DefaultTOP.number")
    reminders = relationship("MeetingReminder", backref=backref("protocoltype"), cascade="all, delete-orphan", order_by="MeetingReminder.days_before")

    def __init__(self, name, short_name, organization,
        is_public, private_group, public_group, private_mail, public_mail):
        self.name = name
        self.short_name = short_name
        self.organization = organization
        self.is_public = is_public
        self.private_group = private_group
        self.public_group = public_group
        self.private_mail = private_mail
        self.public_mail = public_mail

    def __repr__(self):
        return "<ProtocolType(id={}, short_name={}, name={}, organization={}, is_public={}, private_group={}, public_group={})>".format(
            self.id, self.short_name, self.name, self.organization, self.is_public, self.private_group, self.public_group)

    def get_latest_protocol(self):
        candidates = sorted([protocol for protocol in self.protocols if protocol.is_done()], key=lambda p: p.data, reverse=True)
        if len(candidates) == 0:
            return None
        return candidates[0]

    def has_public_view_right(self, user):
        return (self.is_public
            or (user is not None and 
                ((self.public_group != "" and self.public_group in user.groups)
                or (self.private_group != "" and self.private_group in user.groups))))

    def has_private_view_right(self, user):
        return (self.private_group != "" and self.private_group in user.groups)

    def has_modify_right(self, user):
        return self.has_private_view_right(user)


class Protocol(db.Model):
    __tablename__ = "protocols"
    id = db.Column(db.Integer, primary_key=True)
    protocoltype_id = db.Column(db.Integer, db.ForeignKey("protocoltypes.id"))
    source = db.Column(db.String, nullable=True)
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

    def __init__(self, protocoltype_id, date, source=None, start_time=None, end_time=None, author=None, participants=None, location=None):
        self.protocoltype_id = protocoltype_id
        self.date = date
        self.source = source
        self.start_time = start_time
        self.end_time = end_time
        self.author = author
        self.participants = participants
        self.location = location

    def __repr__(self):
        return "<Protocol(id={}, protocoltype_id={})>".format(
            self.id, self.protocoltype_id)

    def create_error(self, action, name, description):
        now = datetime.now()
        return Error(self.id, action, name, now, description)

    def fill_from_remarks(self, remarks):
        self.date = datetime.strptime(remarks["Datum"].value, "%d.%m.%Y")
        self.start_time = time.strptime(remarks["Beginn"].value, "%H:%M")
        self.end_time = time.strptime(remarks["Ende"].value, "%H:%M")
        self.author = remarks["Autor"].value
        self.participants = remarks["Anwesende"].value
        self.location = remarks["Ort"].value

    def is_done(self):
        return self.done


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
    number = db.Column(db.String)
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
    filename = db.Column(db.String, unique=True)
    is_compiled = db.Column(db.Boolean)

    def __init__(self, protocol_id, name, filename, is_compiled):
        self.protocol_id = protocol_id
        self.name = name
        self.filename = filename
        self.is_compiled = is_compiled

    def __repr__(self):
        return "<Document(id={}, protocol_id={}, name={}, filename={}, is_compiled={})>".format(
            self.id, self.protocol_id, self.name, self.filename, self.is_compiled)

class Todo(db.Model):
    __tablename__ = "todos"
    id = db.Column(db.Integer, primary_key=True)
    who = db.Column(db.String)
    description = db.Column(db.String)
    tags = db.Column(db.String)
    done = db.Column(db.Boolean)

    protocols = relationship("Protocol", secondary="todoprotocolassociations", backref="todos")

    def __init__(self, who, description, tags, done):
        self.who = who
        self.description = description
        self.tags = tags
        self.done = done

    def __repr__(self):
        return "<Todo(id={}, who={}, description={}, tags={}, done={})>".format(
            self.id, self.who, self.description, self.tags, self.done)

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
