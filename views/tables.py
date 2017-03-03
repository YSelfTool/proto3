# coding: utf-8
from flask import Markup, url_for, request
from models.database import Protocol, ProtocolType, DefaultTOP, TOP, Todo, Decision, Meta, DefaultMeta
from shared import date_filter, datetime_filter, date_filter_short, current_user, check_login 

import config

class Table:
    def __init__(self, title, values, newlink=None, newtext=None):
        self.title = title
        self.values = values
        self.newlink = newlink
        self.newtext = newtext or "Neu"

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
        return "Ja" if value else "Nein"

    @staticmethod
    def concat(values):
        return Markup(", ".join(values))
        #if len(values) <= 1:
        #    return "".join(values)
        #else:
        #    return "{} and {}".format(", ".join(values[:-1]), values[-1])
            

class SingleValueTable:
    def __init__(self, title, value, newlink=None, newtext=None):
        self.title = title
        self.value = value
        self.newlink = newlink if newlink else None
        self.newtext = newtext or "Ändern"

    def rows(self):
        return [self.row()]

class ProtocolsTable(Table):
    def __init__(self, protocols, search_results=None):
        super().__init__("Protokolle", protocols, newlink=url_for("new_protocol"))
        self.search_results = search_results

    def headers(self):
        result = ["ID", "Sitzung", "Datum"]
        state_part = ["Status"]
        search_part = ["Suchergebnis"]
        login_part = ["Typ", "Löschen"]
        if self.search_results is None:
            result.extend(state_part)
        else:
            result.extend(search_part)
        if check_login():
            result.extend(login_part)
        return result

    def row(self, protocol):
        user = current_user()
        result = [
            Table.link(url_for("show_protocol", protocol_id=protocol.id), str(protocol.id)),
            Table.link(url_for("show_protocol", protocol_id=protocol.id), protocol.protocoltype.name),
            date_filter(protocol.date),
        ]
        if self.search_results is None:
            result.append("Fertig" if protocol.is_done() else "Geplant")
        elif protocol in self.search_results:
            result.append(Markup(self.search_results[protocol]))
        print(user, protocol.protocoltype.has_private_view_right(user))
        if check_login():
            if user is not None and protocol.protocoltype.has_private_view_right(user):
                result.append(Table.link(url_for("show_type", type_id=protocol.protocoltype.id), protocol.protocoltype.short_name))
                result.append(Table.link(url_for("delete_protocol", protocol_id=protocol.id), "Löschen", confirm="Bist du dir sicher, dass du das Protokoll {} löschen möchtest?".format(protocol.get_identifier())))
            else:
                result.extend(["", ""])
        return result

class ProtocolTypesTable(Table):
    def __init__(self, types):
        super().__init__("Protokolltypen", types, newlink=url_for("new_type"))

    def headers(self):
        return ["Typ", "Name", "Neuestes Protokoll", ""]

    def row(self, protocoltype):
        protocol = protocoltype.get_latest_protocol()
        user = current_user()
        has_modify_right = protocoltype.has_modify_right(user)
        return [
            Table.link(url_for("show_type", type_id=protocoltype.id), protocoltype.short_name) if has_modify_right else protocoltype.short_name,
            protocoltype.name,
            Table.link(url_for("show_protocol", protocol_id=protocol.id), protocol.get_identifier()) if protocol is not None else "Noch kein Protokoll",
            Table.link(url_for("new_protocol", type_id=protocoltype.id), "Neues Protokoll") if has_modify_right else ""
            "" # TODO: add link for modify, delete
        ]

class ProtocolTypeTable(SingleValueTable):
    def __init__(self, protocoltype):
        super().__init__(protocoltype.name, protocoltype, newlink=url_for("edit_type", type_id=protocoltype.id))

    def headers(self):
        general_headers = ["Name", "Abkürzung", "Organisation", "Beginn",
            "Öffentlich", "Bearbeitungsgruppe", "Interne Gruppe",
            "Öffentliche Gruppe"]
        mail_headers = ["Interner Verteiler", "Öffentlicher Verteiler"]
        if not config.MAIL_ACTIVE:
            mail_headers = []
        printing_headers = ["Drucker"] if config.PRINTING_ACTIVE else []
        wiki_headers = ["Wiki"]
        if self.value.use_wiki:
            wiki_headers.append("Wiki-Kategorie")
        if not config.WIKI_ACTIVE:
            wiki_headers = []
        calendar_headers = ["Kalender"]
        if not config.CALENDAR_ACTIVE:
            calendar_headers = []
        action_headers = ["Aktion"]
        return (general_headers + mail_headers + printing_headers
           + wiki_headers + calendar_headers + action_headers)

    def row(self):
        general_part = [
            self.value.name,
            self.value.short_name,
            self.value.organization,
            self.value.usual_time.strftime("%H:%M") if self.value.usual_time is not None else "", # todo: remove if, this field is required
            Table.bool(self.value.is_public),
            self.value.modify_group,
            self.value.private_group,
            self.value.public_group,
        ]
        mail_part = [
            self.value.private_mail,
            self.value.public_mail,
        ]
        if not config.MAIL_ACTIVE:
            mail_part = []
        printing_part = [self.value.printer]
        if not config.PRINTING_ACTIVE:
            printing_part = []
        wiki_part = [
            (Table.bool(self.value.use_wiki) + ((", " + ("Öffentlich" if self.value.wiki_only_public else "Intern")) if self.value.use_wiki else ""))
        ]
        if self.value.use_wiki:
            wiki_part.append(self.value.wiki_category)
        if not config.WIKI_ACTIVE:
            wiki_part = []
        calendar_part = [self.value.calendar if self.value.calendar is not None else ""]
        if not config.CALENDAR_ACTIVE:
            calendar_part = []
        action_part = [Table.link(url_for("delete_type", type_id=self.value.id), "Löschen", confirm="Bist du dir sicher, dass du den Protokolltype {} löschen möchtest?".format(self.value.name))]
        return general_part + mail_part + printing_part + wiki_part + calendar_part + action_part

class DefaultTOPsTable(Table):
    def __init__(self, tops, protocoltype=None):
        super().__init__("Standard-TOPs", tops, newlink=url_for("new_default_top", type_id=protocoltype.id) if protocoltype is not None else None)
        self.protocoltype = protocoltype

    def headers(self):
        return ["TOP", "Sortierung", ""]

    def row(self, top):
        return [
            top.name,
            top.number,
            Table.concat([
                Table.link(url_for("move_default_top", type_id=self.protocoltype.id, top_id=top.id, diff=1), "Runter"),
                Table.link(url_for("move_default_top", type_id=self.protocoltype.id, top_id=top.id, diff=-1), "Hoch"),
                Table.link(url_for("edit_default_top", type_id=self.protocoltype.id, top_id=top.id), "Ändern"),
                Table.link(url_for("delete_default_top", type_id=self.protocoltype.id, top_id=top.id), "Löschen", confirm="Bist du dir sicher, dass du den Standard-TOP {} löschen willst?".format(top.name))
            ])
        ]

class MeetingRemindersTable(Table):
    def __init__(self, reminders, protocoltype=None):
        super().__init__("Einladungsmails", reminders, newlink=url_for("new_reminder", type_id=protocoltype.id) if protocoltype is not None else None)
        self.protocoltype = protocoltype

    def headers(self):
        return ["Zeit", "Einladen", "Zusätzlicher Mailinhalt", ""]

    def row(self, reminder):
        return [
            "{} Tage".format(reminder.days_before),
            self.get_send_summary(reminder),
            reminder.additional_text or "",
            Table.concat([
                Table.link(url_for("edit_reminder", type_id=self.protocoltype.id, reminder_id=reminder.id), "Ändern"),
                Table.link(url_for("delete_reminder", type_id=self.protocoltype.id, reminder_id=reminder.id), "Löschen", confirm="Bist du dir sicher, dass du die Einladungsmail {} Tage vor der Sitzung löschen willst?".format(reminder.days_before))
            ])
        ]

    def get_send_summary(self, reminder):
        parts = []
        if reminder.send_public:
            parts.append("Öffentlich")
        if reminder.send_private:
            parts.append("Intern")
        return " und ".join(parts)

class ErrorsTable(Table):
    def __init__(self, errors):
        super().__init__("Fehler", errors)

    def headers(self):
        return ["Protokoll", "Aktion", "Fehler", "Zeitpunkt", "Beschreibung", ""]

    def row(self, error):
        return [
            Table.link(url_for("show_protocol", protocol_id=error.protocol.id), error.protocol.get_identifier()),
            error.action,
            Table.link(url_for("show_error", error_id=error.id), error.name),
            datetime_filter(error.datetime),
            error.get_short_description(),
            Table.link(url_for("delete_error", error_id=error.id, next=request.path), "Löschen", confirm="Bist du dir sicher, dass du den Fehler löschen möchtest?")
        ]

class ErrorTable(SingleValueTable):
    def __init__(self, error):
        super().__init__(error.action, error)

    def headers(self):
        return ["Protokoll", "Aktion", "Fehler", "Zeitpunkt", "Beschreibung"]

    def row(self):
        return [
            Table.link(url_for("show_protocol", protocol_id=self.value.protocol.id), self.value.protocol.get_identifier()),
            self.value.action,
            self.value.name,
            datetime_filter(self.value.datetime),
            Markup("<pre>{}</pre>".format(self.value.description))
        ]

class TodosTable(Table):
    def __init__(self, todos):
        super().__init__("Todos", todos, newlink=url_for("new_todo"))

    def headers(self):
        return ["ID", "Status", "Sitzung", "Name", "Aufgabe", ""]

    def row(self, todo):
        user = current_user()
        protocol = todo.get_first_protocol()
        row = [
            Table.link(url_for("show_todo", todo_id=todo.id), todo.get_id()),
            todo.get_state(),
            Table.link(url_for("show_protocol", protocol_id=protocol.id), protocol.get_identifier())
                if protocol is not None
                else Table.link(url_for("list_protocols", protocoltype=todo.protocoltype.id), todo.protocoltype.short_name),
            todo.who,
            todo.description,
        ]
        if todo.protocoltype.has_modify_right(user):
            row.append(Table.concat([
                Table.link(url_for("edit_todo", todo_id=todo.id), "Ändern"),
                Table.link(url_for("delete_todo", todo_id=todo.id), "Löschen")
            ]))
        else:
            row.append("")
        return row

class TodoTable(SingleValueTable):
    def __init__(self, todo):
        super().__init__("Todo", todo)

    def headers(self):
        return ["ID", "Status", "Sitzung", "Name", "Aufgabe", ""]

    def row(self):
        user = current_user()
        protocol = self.value.get_first_protocol()
        row = [
            self.value.get_id(),
            self.value.get_state_plain(),
            Table.concat([
                Table.link(url_for("show_protocol", protocol_id=protocol.id), protocol.get_identifier())
                    for protocol in self.value.protocols
            ]),
            self.value.who,
            self.value.description
        ]
        if self.value.protocoltype.has_modify_right(user):
            row.append(Table.concat([
                Table.link(url_for("edit_todo", todo_id=self.value.id), "Ändern"),
                Table.link(url_for("delete_todo", todo_id=self.value.id), "Löschen", confirm="Bist du dir sicher, dass du das Todo löschen willst?")
            ]))
        else:
            row.append("")
        return row

class DecisionsTable(Table):
    def __init__(self, decisions):
        super().__init__("Beschlüsse", decisions)

    def headers(self):
        return ["Sitzung", "Beschluss", ""]

    def row(self, decision):
        user = current_user()
        return [
            Table.link(url_for("show_protocol", protocol_id=decision.protocol.id), decision.protocol.get_identifier()),
            decision.content,
            Table.link(url_for("print_decision", document_id=decision.document.id), "Drucken")
                if config.PRINTING_ACTIVE
                and decision.protocol.protocoltype.has_modify_right(user)
                and decision.document is not None 
                else ""
        ]

class DocumentsTable(Table):
    def __init__(self, documents):
        super().__init__("Anhang", documents)

    def headers(self):
        return ["ID", "Name", ""]

    def row(self, document):
        user = current_user()
        links = [Table.link(url_for("delete_document", document_id=document.id), "Löschen", confirm="Bist du dir sicher, dass du das Dokument {} löschen willst?".format(document.name))]
        if config.PRINTING_ACTIVE:
            links.append(Table.link(url_for("print_document", document_id=document.id), "Drucken"))
        return [
            document.id,
            Table.link(url_for("download_document", document_id=document.id), document.name),
            Table.concat(links)
                if document.protocol.protocoltype.has_modify_right(user)
                else ""
        ]

class TodoMailsTable(Table):
    def __init__(self, todomails):
        super().__init__("Todo-Mail-Zuordnungen", todomails, url_for("new_todomail"))

    def headers(self):
        return ["Name", "Mail", ""]

    def row(self, todomail):
        return [
            todomail.name,
            todomail.mail,
            Table.concat([
                Table.link(url_for("edit_todomail", todomail_id=todomail.id), "Ändern"),
                Table.link(url_for("delete_todomail", todomail_id=todomail.id), "Löschen", confirm="Bist du dir sicher, dass du die Todomailzuordnung {} zu {} löschen willst?".format(todomail.name, todomail.mail))
            ])
        ]

class DefaultMetasTable(Table):
    def __init__(self, metas, protocoltype):
        super().__init__(
            "Metadatenfelder",
            metas,
            url_for("new_defaultmeta", type_id=protocoltype.id)
        )

    def headers(self):
        return ["Name", "Key", ""]

    def row(self, meta):
        return [
            meta.name,
            meta.key,
            Table.concat([
                Table.link(url_for("edit_defaultmeta", meta_id=meta.id), "Ändern"),
                Table.link(url_for("delete_defaultmeta", meta_id=meta.id, confirm="Bist du dir sicher, dass du das Metadatenfeld {} löschen willst?".format(meta.name)), "Löschen")
            ])
        ]
