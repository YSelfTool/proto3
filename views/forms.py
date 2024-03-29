from flask_wtf import FlaskForm
from wtforms import (
    StringField, PasswordField, BooleanField, IntegerField, SelectField,
    FileField, DateTimeField, TextAreaField, Field, FormField, DateField,
    widgets)
from wtforms.validators import InputRequired, Optional

import ipaddress

from models.database import TodoState
from validators import CheckTodoDateByState
from shared import current_user

from shared import config


def get_protocoltype_choices(protocoltypes, add_all=True):
    choices = [
        (protocoltype.id, protocoltype.short_name)
        for protocoltype
        in sorted(protocoltypes, key=lambda t: t.short_name)
    ]
    if add_all:
        choices.insert(0, (-1, "Alle Typen"))
    return choices


def get_category_choices(categories, add_all=True):
    choices = [
        (category.id, category.name)
        for category
        in sorted(categories, key=lambda c: c.name)
    ]
    if add_all:
        choices.insert(0, (-1, "Alle Kategorien"))
    return choices


def get_todostate_choices():
    return [
        (state, state.get_name())
        for state in TodoState
    ]


def get_calendar_choices(protocoltype=None):
    from calendarpush import Client as CalendarClient
    calendars = CalendarClient().get_calendars()
    choices = []
    if calendars is not None:
        calendars = sorted(calendars)
        choices = list(zip(calendars, calendars))
    else:
        if (protocoltype is not None
                and protocoltype.calendar is not None
                and protocoltype.calendar != ""):
            choices.append((protocoltype.calendar, protocoltype.calendar))
    choices.insert(0, ("", "Kein Kalender"))
    return choices


def get_printer_choices():
    choices = []
    if config.PRINTING_ACTIVE and config.PRINTING_PRINTERS is not None:
        choices = list(zip(config.PRINTING_PRINTERS, config.PRINTING_PRINTERS))
    choices.insert(0, ("", "Nicht drucken"))
    return choices


def get_latex_template_choices():
    choices = []
    _latex_templates = getattr(config, "LATEX_TEMPLATES", None)
    if _latex_templates is not None:
        choices = [
            (key, values['name'])
            for key, values
            in _latex_templates.items()
        ]
    choices.insert(0, ("", "Standardvorlage"))
    return choices


def get_group_choices():
    user = current_user()
    groups = sorted(user.all_groups)
    choices = list(zip(groups, groups))
    choices.insert(0, ("", "Keine Gruppe"))
    return choices


def coerce_todostate(key):
    if isinstance(key, str):
        class_part, key_part = key.split(".")
        key = TodoState[key_part]
    return key


class IPNetworkField(Field):
    widget = widgets.TextInput()

    def __init__(self, label=None, validators=None, **kwargs):
        super().__init__(label, validators, **kwargs)

    def _value(self):
        if self.raw_data:
            return " ".join(self.raw_data)
        else:
            return self.data and str(self.data) or ""

    def process_formdata(self, valuelist):
        if valuelist:
            data_str = valuelist[0]
            result_parts = []
            try:
                for part in data_str.split(","):
                    part = part.strip()
                    if len(part) > 0:
                        network = ipaddress.ip_network(part)
                        result_parts.append(network)
            except ValueError as exc:
                print(exc)
                self.data = None
                raise ValueError(
                    self.gettext("Not a valid IP Network: {}".format(
                        str(exc))))
            self.data = ",".join(map(str, result_parts))


class FocusedStringField(StringField):
    def __call__(self, **kwargs):
        kwargs['autofocus'] = True
        return super().__call__(**kwargs)


class LoginForm(FlaskForm):
    username = FocusedStringField(
        "Benutzer",
        validators=[InputRequired("Bitte gib deinen Benutzernamen ein.")])
    password = PasswordField(
        "Passwort",
        validators=[InputRequired("Bitte gib dein Passwort ein.")])
    permanent = BooleanField("Eingeloggt bleiben?")


class ProtocolTypeForm(FlaskForm):
    name = StringField(
        "Name",
        validators=[InputRequired("Du musst einen Namen angeben.")])
    short_name = StringField(
        "Abkürzung",
        validators=[InputRequired("Du musst eine Abkürzung angebene.")])
    organization = StringField(
        "Organisation",
        validators=[
            InputRequired("Du musst eine zugehörige Organisation angeben.")
        ])
    usual_time = DateTimeField(
        "Üblicher Beginn",
        validators=[
            InputRequired("Bitte gib die Zeit an, zu der die Sitzung beginnt.")
        ],
        format="%H:%M")
    is_public = BooleanField("Öffentlich sichtbar")
    publish_group = SelectField("Verwaltungsgruppe", choices=[])
    modify_group = SelectField("Bearbeitungsgruppe", choices=[])
    private_group = SelectField("Interne Gruppe", choices=[])
    public_group = SelectField("Öffentliche Gruppe", choices=[])
    non_reproducible_pad_links = BooleanField(
        "nicht nachvollziehbare Etherpad-Links")
    private_mail = StringField("Interner Verteiler")
    public_mail = StringField("Öffentlicher Verteiler")
    wiki_category = StringField("Wiki-Kategorie")
    use_wiki = BooleanField("Wiki benutzen")
    wiki_only_public = BooleanField("Wiki ist öffentlich")
    printer = SelectField("Drucker", choices=[])
    calendar = SelectField("Kalender", choices=[])
    recurrence = IntegerField("Turnus (in Tagen)", validators=[Optional()])
    restrict_networks = BooleanField("Netzwerke einschränken")
    allowed_networks = IPNetworkField("Erlaubte Netzwerke")
    latex_template = SelectField("LaTeX Vorlage", choices=[])

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        protocoltype = kwargs["obj"] if "obj" in kwargs else None
        self.calendar.choices = get_calendar_choices(protocoltype=protocoltype)
        self.printer.choices = get_printer_choices()
        self.latex_template.choices = get_latex_template_choices()
        group_choices = get_group_choices()
        self.publish_group.choices = group_choices
        self.modify_group.choices = group_choices
        self.private_group.choices = group_choices
        self.public_group.choices = group_choices


class DefaultTopForm(FlaskForm):
    name = StringField(
        "Name",
        validators=[InputRequired("Du musst einen Namen angeben.")])
    number = IntegerField(
        "Priorität",
        validators=[InputRequired("Du musst eine Priorität angeben.")])
    description = TextAreaField("Standardinhalt")


class MeetingReminderForm(FlaskForm):
    days_before = IntegerField(
        "Tage vor Sitzung",
        validators=[InputRequired("Du musst eine Dauer angeben.")])
    send_public = BooleanField("Öffentlich einladen")
    send_private = BooleanField("Intern einladen")
    additional_text = TextAreaField("Zusätzlicher Mailinhalt")


class NewProtocolForm(FlaskForm):
    protocoltype_id = SelectField("Typ", choices=[], coerce=int)
    date = DateField(
        "Datum",
        validators=[InputRequired("Du musst ein Datum angeben.")])
    start_time = DateTimeField(
        "Uhrzeit (HH:MM, optional)",
        validators=[Optional()],
        format="%H:%M")

    def __init__(self, protocoltypes, **kwargs):
        super().__init__(**kwargs)
        self.protocoltype_id.choices = get_protocoltype_choices(
            protocoltypes, add_all=False)


class DocumentEditForm(FlaskForm):
    name = StringField("Dateiname")
    is_private = BooleanField("Intern")


class DocumentUploadForm(FlaskForm):
    document = FileField("Datei")
    is_private = BooleanField("Intern")


class KnownProtocolSourceUploadForm(FlaskForm):
    source = FileField("Quellcode")


class NewProtocolSourceUploadForm(FlaskForm):
    source = FileField("Quellcode")
    protocoltype_id = SelectField("Typ", choices=[], coerce=int)

    def __init__(self, protocoltypes, **kwargs):
        super().__init__(**kwargs)
        self.protocoltype_id.choices = get_protocoltype_choices(
            protocoltypes, add_all=False)


class NewProtocolFileUploadForm(FlaskForm):
    file = FileField("Datei")
    protocoltype_id = SelectField("Typ", choices=[], coerce=int)
    private = BooleanField("Intern")

    def __init__(self, protocoltypes, **kwargs):
        super().__init__(**kwargs)
        self.protocoltype_id.choices = get_protocoltype_choices(
            protocoltypes, add_all=False)


def generate_protocol_form(protocol):
    class ProtocolMetasForm(FlaskForm):
        pass
    for meta in protocol.metas:
        setattr(ProtocolMetasForm, meta.name, StringField(meta.name))

    class ProtocolForm(FlaskForm):
        date = DateField(
            "Datum",
            validators=[
                InputRequired("Bitte gib das Datum des Protkolls an.")
            ])
        start_time = DateTimeField(
            "Beginn (%H:%M)", format="%H:%M", validators=[Optional()])
        end_time = DateTimeField(
            "Ende (%H:%M)", format="%H:%M", validators=[Optional()])
        metas = FormField(ProtocolMetasForm)
        done = BooleanField("Fertig")
        public = BooleanField("Veröffentlicht")
    return ProtocolForm


class TopForm(FlaskForm):
    name = StringField(
        "TOP",
        validators=[InputRequired("Du musst den Namen des TOPs angeben.")])
    number = IntegerField(
        "Priorität",
        validators=[InputRequired("Du musst eine Priorität angeben.")])
    description = TextAreaField("Beschreibung")


class LocalTopForm(FlaskForm):
    description = TextAreaField("Beschreibung")


class SearchForm(FlaskForm):
    search = StringField("Suchbegriff")
    protocoltype_id = SelectField("Typ", choices=[], coerce=int)

    def __init__(self, protocoltypes, **kwargs):
        super().__init__(**kwargs)
        self.protocoltype_id.choices = get_protocoltype_choices(protocoltypes)


class DecisionSearchForm(SearchForm):
    decisioncategory_id = SelectField("Kategorie", choices=[], coerce=int)

    def __init__(self, protocoltypes, categories, **kwargs):
        super().__init__(protocoltypes=protocoltypes, **kwargs)
        self.decisioncategory_id.choices = get_category_choices(categories)


class ProtocolSearchForm(SearchForm):
    state_open = SelectField(
        "Offen",
        choices=[(-1, "Alle"), (0, "Geplant"), (1, "Fertig")],
        coerce=int)


class TodoSearchForm(SearchForm):
    state_open = SelectField(
        "Offen",
        choices=[(-1, "Alle"), (0, "Offen"), (1, "Erledigt")],
        coerce=int)


class NewTodoForm(FlaskForm):
    protocoltype_id = SelectField("Typ", choices=[], coerce=int)
    who = StringField(
        "Person",
        validators=[
            InputRequired("Bitte gib an, wer das Todo erledigen soll.")
        ])
    description = StringField(
        "Aufgabe", validators=[
            InputRequired("Bitte gib an, was erledigt werden soll.")
        ])
    state = SelectField(
        "Status",
        choices=[],
        coerce=coerce_todostate,
        validators=[CheckTodoDateByState()])
    date = DateField("Datum", validators=[Optional()])

    def __init__(self, protocoltypes, **kwargs):
        super().__init__(**kwargs)
        self.protocoltype_id.choices = get_protocoltype_choices(
            protocoltypes, add_all=False)
        self.state.choices = get_todostate_choices()


class TodoForm(FlaskForm):
    who = StringField("Person")
    description = StringField(
        "Aufgabe",
        validators=[InputRequired("Bitte gib an, was erledigt werden soll.")])
    state = SelectField(
        "Status",
        choices=[],
        coerce=coerce_todostate,
        validators=[CheckTodoDateByState()])
    date = DateField("Datum", validators=[Optional()])

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.state.choices = get_todostate_choices()


class TodoMailForm(FlaskForm):
    name = StringField(
        "Name",
        validators=[
            InputRequired("Du musst den Namen angeben, der zugeordnet werden "
                          "soll.")])
    mail = StringField(
        "Mail",
        validators=[
            InputRequired("Du musst die Mailadresse angeben, die zugeordnet "
                          "werden soll.")])


class MetaForm(FlaskForm):
    name = StringField(
        "Name",
        validators=[InputRequired("Bitte gib den Namen der Metadaten an.")])
    value = StringField("Wert")
    internal = BooleanField("Intern")


class DefaultMetaForm(FlaskForm):
    key = StringField(
        "Key",
        validators=[
            InputRequired("Bitte gib den Protokoll-Syntax-Schlüssel der "
                          "Metadaten an.")
        ])
    name = StringField(
        "Name",
        validators=[InputRequired("Bitte gib den Namen der Metadaten an.")])
    value = StringField("Standardwert")
    internal = BooleanField("Intern")
    prior = BooleanField("Planungsrelevant")


class DecisionCategoryForm(FlaskForm):
    name = StringField(
        "Name",
        validators=[InputRequired("Bitte gib den Namen der Kategorie an.")])


class MergeTodosForm(FlaskForm):
    todo1 = IntegerField("todo 1", validators=[InputRequired()])
    todo2 = IntegerField("todo 2", validators=[InputRequired()])

    def __init__(self, todo=None):
        if todo is not None:
            self.todo1.data = todo.id
