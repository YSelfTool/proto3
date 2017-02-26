from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, BooleanField, DateField, HiddenField, IntegerField, SelectField, FileField, DateTimeField, TextAreaField
from wtforms.validators import InputRequired, Optional

import config

def get_protocoltype_choices(protocoltypes, add_all=True):
    choices = [(protocoltype.id, protocoltype.short_name) for protocoltype in protocoltypes]
    if add_all:
        choices.insert(0, (-1, "Alle"))
    return choices

class LoginForm(FlaskForm):
    username = StringField("Benutzer", validators=[InputRequired("Bitte gib deinen Benutzernamen ein.")])
    password = PasswordField("Passwort", validators=[InputRequired("Bitte gib dein Passwort ein.")])

class ProtocolTypeForm(FlaskForm):
    name = StringField("Name", validators=[InputRequired("Du musst einen Namen angeben.")])
    short_name = StringField("Abkürzung", validators=[InputRequired("Du musst eine Abkürzung angebene.")])
    organization = StringField("Organisation", validators=[InputRequired("Du musst eine zugehörige Organisation angeben.")])
    usual_time = DateTimeField("Üblicher Beginn", validators=[InputRequired("Bitte gib die Zeit an, zu der die Sitzung beginnt.")], format="%H:%M")
    is_public = BooleanField("Öffentlich sichtbar")
    private_group = StringField("Interne Gruppe")
    public_group = StringField("Öffentliche Gruppe")
    private_mail = StringField("Interner Verteiler")
    public_mail = StringField("Öffentlicher Verteiler")
    wiki_category = StringField("Wiki-Kategorie")
    use_wiki = BooleanField("Wiki benutzen")
    wiki_only_public = BooleanField("Wiki ist öffentlich")
    printer = SelectField("Drucker", choices=list(zip(config.PRINTING_PRINTERS, config.PRINTING_PRINTERS)))

class DefaultTopForm(FlaskForm):
    name = StringField("Name", validators=[InputRequired("Du musst einen Namen angeben.")])
    number = IntegerField("Nummer", validators=[InputRequired("Du musst eine Nummer angeben.")])

class MeetingReminderForm(FlaskForm):
    days_before = IntegerField("Tage vor Sitzung", validators=[InputRequired("Du musst eine Dauer angeben.")])
    send_public = BooleanField("Öffentlich einladen")
    send_private = BooleanField("Intern einladen")
    additional_text = TextAreaField("Zusätzlicher Mailinhalt")

class NewProtocolForm(FlaskForm):
    protocoltype = SelectField("Typ", choices=[], coerce=int)
    date = DateField("Datum", validators=[InputRequired("Du musst ein Datum angeben.")], format="%d.%m.%Y")

    def __init__(self, protocoltypes, **kwargs):
        super().__init__(**kwargs)
        self.protocoltype.choices = get_protocoltype_choices(protocoltypes, add_all=False)

class DocumentUploadForm(FlaskForm):
    document = FileField("Datei")
    private = BooleanField("Intern")

class KnownProtocolSourceUploadForm(FlaskForm):
    source = FileField("Quellcode")

class NewProtocolSourceUploadForm(FlaskForm):
    source = FileField("Quellcode")
    protocoltype = SelectField("Typ", choices=[], coerce=int)

    def __init__(self, protocoltypes, **kwargs):
        super().__init__(**kwargs)
        self.protocoltype.choices = get_protocoltype_choices(protocoltypes, add_all=False)

class NewProtocolFileUploadForm(FlaskForm):
    file = FileField("Datei")
    protocoltype = SelectField("Typ", choices=[], coerce=int)
    private = BooleanField("Intern")

    def __init__(self, protocoltypes, **kwargs):
        super().__init__(**kwargs)
        self.protocoltype.choices = get_protocoltype_choices(protocoltypes, add_all=False)

class ProtocolForm(FlaskForm):
    date = DateField("Datum", validators=[InputRequired("Bitte gib das Datum des Protkolls an.")], format="%d.%m.%Y")
    start_time = DateTimeField("Beginn", format="%H:%M", validators=[Optional()])
    end_time = DateTimeField("Ende", format="%H:%M", validators=[Optional()])
    location = StringField("Ort")
    author = StringField("Protokollant")
    participants = StringField("Anwesende")
    done = BooleanField("Fertig")

class TopForm(FlaskForm):
    name = StringField("TOP", validators=[InputRequired("Du musst den Namen des TOPs angeben.")])
    number = IntegerField("Sortierung", validators=[InputRequired("Du musst eine Sortierung in der Reihenfolge angebene.")])

class SearchForm(FlaskForm):
    search = StringField("Suchbegriff")
    protocoltype = SelectField("Typ", choices=[], coerce=int)

    def __init__(self, protocoltypes, **kwargs):
        super().__init__(**kwargs)
        self.protocoltype.choices = get_protocoltype_choices(protocoltypes)

class NewTodoForm(FlaskForm):
    protocoltype_id = SelectField("Typ", choices=[], coerce=int)
    who = StringField("Person", validators=[InputRequired("Bitte gib an, wer das Todo erledigen soll.")])
    description = StringField("Aufgabe", validators=[InputRequired("Bitte gib an, was erledigt werden soll.")])
    tags = StringField("Weitere Tags")
    done = BooleanField("Erledigt")
    
    def __init__(self, protocoltypes, **kwargs):
        super().__init__(**kwargs)
        self.protocoltype_id.choices = get_protocoltype_choices(protocoltypes, add_all=False)

class TodoForm(FlaskForm):
    who = StringField("Person")
    description = StringField("Aufgabe", validators=[InputRequired("Bitte gib an, was erledigt werden soll.")])
    tags = StringField("Weitere Tags")
    done = BooleanField("Erledigt")

class TodoMailForm(FlaskForm):
    name = StringField("Name", validators=[InputRequired("Du musst den Namen angeben, der zugeordnet werden soll.")])
    mail = StringField("Mail", validators=[InputRequired("Du musst die Mailadresse angeben, die zugeordnet werden soll.")])
