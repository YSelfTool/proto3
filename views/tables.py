# coding: utf-8
from flask import Markup, url_for, request
from models.database import Protocol, ProtocolType, DefaultTOP, TOP, Todo, Decision
from shared import date_filter

class Table:
    def __init__(self, title, values, newlink=None):
        self.title = title
        self.values = values
        self.newlink = newlink
        self.newtext = "New"

    def rows(self):
        return [row for row in [self.row(value) for value in self.values] if row is not None]

    @staticmethod
    def link(target, text, confirm=None):
        confirmation = ""
        if confirm:
            confirmation = " onclick=\"return confirm('{}');\"".format(confirm)
        return Markup("<a href=\"{}\"{}>{}</a>".format(target, confirmation, text))

    @staticmethod
    def mail(target):
        return Markup("<a href=\"mailto:{}\">{}</a>".format(target, target))

    @staticmethod
    def bool(value):
        return "Yes" if value else "No"

    @staticmethod
    def concat(values):
        return ", ".join(values)
        #if len(values) <= 1:
        #    return "".join(values)
        #else:
        #    return "{} and {}".format(", ".join(values[:-1]), values[-1])
            

class SingleValueTable:
    def __init__(self, title, value, newlink=None):
        self.title = title
        self.value = value
        self.newlink = newlink if newlink else None
        self.newtext = "Edit"

    def rows(self):
        return [self.row()]

class ProtocolsTable(Table):
    def __init__(self, protocols):
        super().__init__("Protokolle", protocols, newlink=None)

    def headers(self):
        return ["ID", "Sitzung", "Datum"]

    def row(self, protocol):
        return [
            Table.link(url_for("protocol_view", protocol_id=protocol.id), str(protocol.id)),
            protocol.protocoltype.name,
            date_filter(protocol.data)
        ]

