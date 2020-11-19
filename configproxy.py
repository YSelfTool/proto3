#!/usr/bin/env python3
import os
from common import auth

import logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def split_line(line, max_length=76):
    words = list(filter(None, map(str.strip, line.split(" "))))
    lines = []
    current_line = []
    current_line_length = 0
    for word in words:
        if (current_line and current_line_length + len(word) + 1 > max_length):
            lines.append(" ".join(current_line))
            current_line = []
            current_line_length = 0
        current_line.append(word)
        current_line_length += len(word) + 1
    if current_line:
        lines.append(" ".join(current_line))
    return lines


def prefix_lines(lines, prefix="#  "):
    return map(lambda line: "".join((prefix, line)), lines)


class ConfigEntry:
    def __init__(self, name, default, required=True, internal=True,
                 immutable=False, no_sane_default=False,
                 description=None, value=None):
        self.name = name
        self.default = default
        self.required = required
        self.internal = internal
        self.immutable = immutable
        self.no_sane_default = no_sane_default
        self.description = description
        self.value = value

    def extract(self, config):
        if self.immutable:
            self.value = self.default
            return
        if not hasattr(config, self.name) and self.required:
            raise ValueError(
                "Missing required config entry {}!".format(self.name))
        self.value = getattr(config, self.name, self.default)
        if self.no_sane_default and self.value == self.default:
            raise ValueError(
                "You have not configured {}, which is required!".format(
                    self.name))

    def get_example(self):
        if self.immutable:
            return []
        lines = []
        if self.description is not None:
            lines.extend(prefix_lines(split_line(self.description)))
        entry_line = "{} = {}".format(self.name, repr(self.default))
        if not self.required:
            entry_line = "# {}".format(entry_line)
        lines.append(entry_line)
        return lines


class ConfigSection:
    def __init__(self, name, entries, check, description=None,
                 deactivatable=False, active=None, imports=None):
        self.name = name
        self.entries = entries
        self.check = check
        self.description = description
        self.deactivatable = deactivatable
        self.active = active
        if isinstance(imports, str):
            imports = [imports]
        self.imports = imports

    def extract(self, config):
        if self.deactivatable:
            self.active = getattr(config, "{}_ACTIVE".format(self.name), False)
            if not self.active:
                return
        for entry in self.entries:
            entry.extract(config)

    def get_example(self):
        lines = []
        if self.imports:
            lines.extend(self.imports)
        header_line = (
            "# [{}]".format(self.name) +
            (" (optional)" if self.deactivatable else ""))
        lines.append(header_line)
        if self.description is not None:
            lines.extend(prefix_lines(split_line(self.description)))
            lines.append("")
        if self.deactivatable:
            lines.extend(prefix_lines(split_line("deactivate with")))
            lines.append("# {}_ACTIVE = False".format(self.name))
            lines.append("")
        for entry in self.entries:
            lines.extend(entry.get_example())
            lines.append("")
        lines.append("")
        return "\n".join(lines)

    def fill_modules(self, config, public_config):
        if self.deactivatable:
            setattr(config, "{}_ACTIVE".format(self.name), self.active)
            setattr(public_config, "{}_ACTIVE".format(self.name), self.active)
            if not self.active:
                return
        for entry in self.entries:
            setattr(config, entry.name, entry.value)
            if not entry.internal:
                setattr(public_config, entry.name, entry.value)


def check_choice(option, value, choices):
    if value not in choices:
        raise ValueError(
            "{} is not allowed choices! Should be one of {}, is {}".format(
                option, choices, value))


def check_database(
        SQLALCHEMY_DATABASE_URI,
        SQLALCHEMY_TRACK_MODIFICATIONS):
    # remove once sqlalchemy.database_exists works as intended
    return True
    from sqlalchemy_utils import database_exists
    from sqlalchemy import exc
    try:
        if not database_exists(SQLALCHEMY_DATABASE_URI):
            raise ValueError(
                "The database '{}' does not exist! "
                "Please configure it correctly or create it!".format(
                    SQLALCHEMY_DATABASE_URI))
    except (exc.NoSuchModuleError, exc.OperationalError) as error:
        raise ValueError(
            "The database uri '{}' does not state a valid "
            "database: {}".format(SQLALCHEMY_DATABASE_URI, error))


def check_security(SECRET_KEY, SECURITY_KEY, SESSION_PROTECTION, SESSION_COOKIE_SECURE, SESSION_COOKIE_HTTPONLY, SESSION_COOKIE_SAMESITE):
    MIN_KEY_LENGTH = 20
    if len(SECRET_KEY) < MIN_KEY_LENGTH:
        raise ValueError(
            "Insufficient length of SECRET_KEY, should be at least {}!".format(
                MIN_KEY_LENGTH))
    if len(SECURITY_KEY) < MIN_KEY_LENGTH:
        raise ValueError(
            "Insufficient length of SECURITY_KEY, should be at "
            "least {}!".format(
                MIN_KEY_LENGTH))
    check_choice("SESSION_PROTECTION", SESSION_PROTECTION, ["strong"])
    check_choice("SESSION_COOKIE_SECURE", SESSION_COOKIE_SECURE, [True, False])
    check_choice("SESSION_COOKIE_HTTPONLY", SESSION_COOKIE_HTTPONLY, [True, False])
    check_choice("SESSION_COOKIE_SAMESITE", SESSION_COOKIE_HTTPONLY, ["Lax", "Strict"])


def check_server_name(SERVER_NAME, PREFERRED_URL_SCHEME, CDN_URL):
    # todo: check ip address and server name
    check_choice(
        "PREFERRED_URL_SCHEME", PREFERRED_URL_SCHEME,
        ["http", "https"])


def check_debug(DEBUG):
    if DEBUG:
        logger.warning("DEBUG mode is activated!")


def check_celery(
        CELERY_BROKER_URL, CELERY_TASK_SERIALIZER, CELERY_ACCEPT_CONTENT):
    pass
    # todo: check broker url
    check_choice(
        "CELERY_TASK_SERIALIZER", CELERY_TASK_SERIALIZER,
        ["pickle"])
    check_choice(
        "CELERY_ACCEPT_CONTENT", CELERY_ACCEPT_CONTENT,
        [["pickle"]])


def check_sentry(SENTRY_DSN):
    pass


def check_authentication(AUTH_MAX_DURATION, AUTH_BACKENDS):
    if AUTH_MAX_DURATION <= 0:
        raise ValueError(
            "AUTH_MAX_DURATION should be positive, is {}!".format(
                AUTH_MAX_DURATION))
    if not AUTH_BACKENDS:
        raise ValueError("No authentication backends have been configured!")


def check_error_report_context(ERROR_CONTEXT_LINES):
    if ERROR_CONTEXT_LINES < 0:
        raise ValueError(
            "ERROR_CONTEXT_LINES should be positive, is {}!".format(
                ERROR_CONTEXT_LINES))


def check_pagination(PAGE_LENGTH, PAGE_DIFF):
    if PAGE_LENGTH <= 0:
        raise ValueError(
            "PAGE_LENGTH should be positive, is {}!".format(
                PAGE_LENGTH))
    if PAGE_DIFF < 0:
        raise ValueError(
            "PAGE_DIFF should be positive, is {}!".format(
                PAGE_DIFF))


def check_index_page(
        MAX_INDEX_DAYS, MAX_PAST_INDEX_DAYS,
        MAX_PAST_INDEX_DAYS_BEFORE_REMINDER):
    if MAX_INDEX_DAYS < 0:
        raise ValueError(
            "MAX_INDEX_DAYS should be positive, is {}!".format(
                MAX_INDEX_DAYS))
    if MAX_PAST_INDEX_DAYS < 0:
        raise ValueError(
            "MAX_PAST_INDEX_DAYS should be positive, is {}!".format(
                MAX_PAST_INDEX_DAYS))
    if MAX_PAST_INDEX_DAYS_BEFORE_REMINDER < 0:
        raise ValueError(
            "MAX_PAST_INDEX_DAYS_BEFORE_REMINDER should be "
            "positive, is {}!".format(
                MAX_PAST_INDEX_DAYS_BEFORE_REMINDER))


def check_admin_data(ADMIN_MAIL, ADMIN_GROUP):
    if not ADMIN_MAIL:
        raise ValueError("No admin mail address given!")
    if not ADMIN_GROUP:
        raise ValueError("No admin group given!")


def check_parser(PARSER_LAZY, FUZZY_MIN_SCORE, PRIVATE_KEYWORDS):
    if PARSER_LAZY:
        logger.warning(
            "Parser lazy mode is activated, this is not meant or useful "
            "for production operation!")
    if not 0 <= FUZZY_MIN_SCORE <= 100:
        raise ValueError(
            "FUZZY_MIN_SCORE should be a percentage from 0 to 100")
    for keyword in PRIVATE_KEYWORDS:
        if not keyword:
            raise ValueError("Invalid private keyword given: {}".format(
                keyword))


def check_rendering(
        FONTS, DOCUMENTS_PATH, LATEX_BULLETPOINTS, HTML_LEVEL_OFFSET,
        LATEX_LOCAL_TEMPLATES, LATEX_LOGO_TEMPLATE, LATEX_GEOMETRY,
        LATEX_PAGESTYLE, LATEX_HEADER_FOOTER, LATEX_ADDITIONAL_PACKAGES,
        LATEX_TEMPLATES):
    for key in ("main", "roman", "sans", "mono"):
        if key not in FONTS:
            raise ValueError("No font for type {} given!".format(key))
        try:
            path = FONTS[key]["path"]
            extension = FONTS[key]["extension"]
            for face in ("regular", "bold", "italic", "bolditalic"):
                if face not in FONTS[key]:
                    raise ValueError("Missing fontface {} for {} font!".format(
                        face, key))
                filepath = os.path.join(
                    path, "".join((FONTS[key][face], extension)))
                if not os.path.exists(filepath):
                    raise ValueError(
                        "Font {} does not exist in the filesystem! "
                        "Expected it at {}".format(
                            FONTS[key][face], filepath))
        except KeyError:
            raise ValueError(
                "Missing path information in font specification "
                "{key}: ".format(key=key))
    if not os.path.isdir(DOCUMENTS_PATH):
        raise ValueError(
            "Document savedir does not exist! Should be at {}.".format(
                DOCUMENTS_PATH))
    if not LATEX_BULLETPOINTS:
        raise ValueError("LATEX_BULLETPOINTS is empty.")
    if not 1 <= HTML_LEVEL_OFFSET <= 4:
        raise ValueError(
            "HTML_LEVEL_OFFSET should be from 1 to 4, but is {}".format(
                HTML_LEVEL_OFFSET))
    # todo: check templates stuff


def check_mail(MAIL_FROM, MAIL_HOST, MAIL_USER, MAIL_PASSWORD,
               MAIL_USE_TLS, MAIL_USE_STARTTLS):
    if MAIL_USE_TLS and MAIL_USE_STARTTLS:
        raise ValueError(
            "Both TLS and STARTTLS are set for Mail! Please set only one.")
    from utils import MailManager
    import socket
    import smtplib
    import ssl
    mail_config = Config()
    mail_config.MAIL_ACTIVE = True
    mail_config.MAIL_FROM = MAIL_FROM
    mail_config.MAIL_HOST = MAIL_HOST
    mail_config.MAIL_USER = MAIL_USER
    mail_config.MAIL_PASSWORD = MAIL_PASSWORD
    mail_config.MAIL_USE_TLS = MAIL_USE_TLS
    mail_config.MAIL_USE_STARTTLS = MAIL_USE_STARTTLS
    mail_manager = MailManager(mail_config)
    try:
        if not mail_manager.check():
            raise ValueError("The mail connection is improperly configured.")
    except (ConnectionRefusedError, socket.gaierror) as error:
        raise ValueError("Mail Cannot connect to the server: {}".format(error))
    except smtplib.SMTPAuthenticationError as error:
        raise ValueError("Mail Cannot authenticate: {}".format(error))
    except (ssl.SSLError, smtplib.SMTPNotSupportedError) as error:
        raise ValueError("TLS for Mail does not work: {}".format(error))
    except Exception as error:
        raise ValueError(
            "Testing the mail connection failed: {}".format(error))


def check_printing(PRINTING_SERVER, PRINTING_USER, PRINTING_PRINTERS):
    LPR_PATH = "/usr/bin/lpr"
    LPSTAT_PATH = "/usr/bin/lpstat"
    LPOPTIONS_PATH = "/usr/bin/lpoptions"
    for path in [LPR_PATH, LPSTAT_PATH, LPOPTIONS_PATH]:
        if not os.path.exists(path):
            raise ValueError(
                "{} is not installed! It is required for printing".format(
                    path))
    import subprocess as sp
    list_printers_command = [LPSTAT_PATH, "-h", PRINTING_SERVER, "-p"]
    raw_printers = sp.check_output(list_printers_command).decode("utf-8")
    printers = [
        line.split(" ")[1].lower()
        for line in raw_printers.splitlines()
        if not line.startswith(" ")
    ]
    configured_printers = [key.lower() for key in PRINTING_PRINTERS]
    missing_printers = set(configured_printers) - set(printers)
    if missing_printers:
        raise ValueError(
            "Some configured printers are not available: {}, "
            "available are: {}".format(
                missing_printers, printers))

    def _strip_star(value):
        if value.startswith("*"):
            return value[1:]
        return value
    for printer in configured_printers:
        options_command = [
            LPOPTIONS_PATH, "-h", PRINTING_SERVER, "-p", printer, "-l"]
        raw_options = sp.check_output(options_command).decode("utf-8")
        available_options = {}
        for line in raw_options.splitlines():
            name_part, value_part = line.split(":")
            values = list(map(_strip_star, value_part.strip().split(" ")))
            for name in name_part.split("/"):
                available_options[name] = values
        for option in PRINTING_PRINTERS[printer]:
            name, value = option.split("=")
            if name not in available_options:
                logger.warning(
                    "Printer {} has unknown option {} set!".format(
                        printer, name))
            elif value not in available_options[name]:
                logger.warning(
                    "Printer {} has the invalid value {} specified "
                    "for option {}! Valid values are {}.".format(
                        printer, value, name, available_options[name]))


def check_etherpad(ETHERPAD_URL, ETHERPAD_API_URL, ETHERPAD_APIKEY, EMPTY_ETHERPAD):
    import requests
    try:
        answer = requests.get(ETHERPAD_URL)
        if answer.status_code != 200:
            raise ValueError(
                "The etherpad does not return 200 OK at {}".format(
                    ETHERPAD_URL))
    except requests.exceptions.ConnectionError as error:
        raise ValueError("Cannot connect to the etherpad at {}: {}".format(
            ETHERPAD_URL, error))


def check_wiki(
        WIKI_TYPE, WIKI_API_URL, WIKI_ANONYMOUS,
        WIKI_USER, WIKI_PASSWORD, WIKI_DOMAIN):
    check_choice("WIKI_TYPE", WIKI_TYPE, ["MEDIAWIKI", "DOKUWIKI"])
    # todo: check the connection


def check_calendar(
        CALENDAR_URL, CALENDAR_DEFAULT_DURATION, CALENDAR_MAX_REQUESTS):
    from calendarpush import Client, CalendarException
    try:
        client = Client(url=CALENDAR_URL)
        client.get_calendars()
    except (KeyError, CalendarException) as error:
        raise ValueError("Cannot connect to the calendar at {}!".format(
            CALENDAR_URL))


def check_timezone(CALENDAR_TIMEZONE_MAP):
    pass


CONFIG_SECTIONS = [
    ConfigSection(
        name="Database",
        entries=[
            ConfigEntry(
                name="SQLALCHEMY_DATABASE_URI",
                default="engine://user:password@host/database",
                required=True, internal=True, no_sane_default=True,
                description=(
                    "Database connection string. See "
                    "http://docs.sqlalchemy.org/en/latest/core/engines.html "
                    "for details. SQLite does not work with Alembic "
                    "migrations.")),
            ConfigEntry(
                name="SQLALCHEMY_TRACK_MODIFICATIONS",
                default=False,
                required=False, internal=True, immutable=True,
                description="Necessary option. Do not change."),
        ],
        check=check_database,
        description="Settings for SQLAlchemy"),
    ConfigSection(
        name="Security",
        entries=[
            ConfigEntry(
                name="SECRET_KEY",
                default=os.urandom(128),
                required=True, internal=True,
                description="Secret random key used for session security."),
            ConfigEntry(
                name="SECURITY_KEY",
                default=os.urandom(128),
                required=True, internal=True,
                description="Secret random key used for user sessions."),
            ConfigEntry(
                name="SESSION_PROTECTION",
                default="strong",
                required=False, internal=True, immutable=True,
                description="Flask setting for sessions. Do not change."),
            ConfigEntry(
                name="SESSION_COOKIE_SECURE",
                default=True,
                required=False, internal=True, immutable=True,
                description="Flask setting for cookies. Do not change."),
            ConfigEntry(
                name="SESSION_COOKIE_HTTPONLY",
                default=True,
                required=False, internal=True, immutable=True,
                description="Flask setting for cookies. Do not change."),
            ConfigEntry(
                name="SESSION_COOKIE_SAMESITE",
                default="Strict",
                required=False, internal=True, immutable=True,
                description="Flask setting for cookies. Do not change."),
        ],
        check=check_security,
        description="Secret keys and random strings"),
    ConfigSection(
        name="URL Root",
        entries=[
            ConfigEntry(
                name="SERVER_NAME",
                default="protokolle.example.com",
                required=True, internal=False, no_sane_default=True,
                description="Domain on which this website is hosted"),
            ConfigEntry(
                name="PREFERRED_URL_SCHEME",
                default="https",
                required=False, internal=False,
                description="Protocol used by this website. "
                            "Either 'http' or 'https'."),
            ConfigEntry(
                name="CDN_URL",
                default=None,
                required=False, internal=False,
                description="URL to get bootstrap and jQuery from.")
        ],
        check=check_server_name,
        description="Where is the website hosted"),
    ConfigSection(
        name="Debug",
        entries=[
            ConfigEntry(
                name="DEBUG",
                default=False,
                required=False, internal=True,
                description="Activate debug mode"),
        ],
        check=check_debug,
        description="Debug mode. Do not set in production."),
    ConfigSection(
        name="Celery",
        entries=[
            ConfigEntry(
                name="CELERY_BROKER_URL",
                default="redis://localhost:6379/0",
                required=True, internal=True,
                description=(
                    "Connection to the celery broker. See http://docs.celery"
                    "project.org/en/latest/userguide/configuration.html")),
            ConfigEntry(
                name="CELERY_TASK_SERIALIZER",
                default="pickle",
                required=False, internal=True, immutable=True,
                description="How celery serializes tasks. Do not change."),
            ConfigEntry(
                name="CELERY_ACCEPT_CONTENT",
                default=['pickle'],
                required=False, internal=True, immutable=True,
                description="How celery deserializes tasks. Do not change."),
        ],
        check=check_celery,
        description="Settings for the task scheduler."),
    ConfigSection(
        name="Sentry",
        entries=[
            ConfigEntry(
                name="SENTRY_DSN",
                default=None,
                required=False, internal=True,
                description=(
                    "Connection string for sentry. See "
                    "https://docs.sentry.io/quickstart/#configure-the-dsn")),
        ],
        check=check_sentry,
        description="Connection information for sentry exception reporting."),
    ConfigSection(
        name="Authentication",
        entries=[
            ConfigEntry(
                name="AUTH_MAX_DURATION",
                default=300,
                required=False, internal=False,
                description="Time in seconds for which non-permanent "
                            "sessions remain valid"),
            ConfigEntry(
                name="AUTH_BACKENDS",
                default=[
                    auth.StaticUserManager((("user", "password", ["group"]),)),
                ],
                required=True, internal=True, no_sane_default=True,
                description="Active Authentication backends"),
        ],
        check=check_authentication,
        description="User Authentication backend settings.",
        imports="from common import auth"),
    ConfigSection(
        name="Error Report Context",
        entries=[
            ConfigEntry(
                name="ERROR_CONTEXT_LINES",
                default=3,
                required=False, internal=False,
                description=(
                    "Number of lines before and after an error to include "
                    "in the error description")),
        ],
        check=check_error_report_context,
        description="Compiling error context settings"),
    ConfigSection(
        name="Pagination",
        entries=[
            ConfigEntry(
                name="PAGE_LENGTH",
                default=20,
                required=False, internal=False,
                description="Default number of entries per page"),
            ConfigEntry(
                name="PAGE_DIFF",
                default=3,
                required=False, internal=False,
                description=(
                    "Number of pages before and after the current one "
                    "with a direct link.")),
        ],
        check=check_pagination,
        description="Pagination settings, used for list pages"),
    ConfigSection(
        name="Index Page",
        entries=[
            ConfigEntry(
                name="MAX_INDEX_DAYS",
                default=14,
                required=False, internal=False,
                description="Next days to list upcoming meetings on"),
            ConfigEntry(
                name="MAX_PAST_INDEX_DAYS",
                default=2,
                required=False, internal=False,
                description="Past days to list unfinished meetings on"),
            ConfigEntry(
                name="MAX_PAST_INDEX_DAYS_BEFORE_REMINDER",
                default=14,
                required=False, internal=True,
                description=(
                    "If a meeting is unfinished this many days after its "
                    "date, a reminder is sent by mail")),
        ],
        check=check_index_page,
        description="Settings for what to show on the index page"),
    ConfigSection(
        name="Admin data",
        entries=[
            ConfigEntry(
                name="ADMIN_MAIL",
                default="admin@example.com",
                required=True, internal=False, no_sane_default=True,
                description="Mail address to tell users to "
                            "contact in case of errors"),
            ConfigEntry(
                name="ADMIN_GROUP",
                default="admin",
                required=True, internal=False,
                description="Users with this group are admins and are "
                            "allowed to do and see everything."),
        ],
        check=check_admin_data,
        description="Settings for who is an admin and how to contact them"),
    ConfigSection(
        name="Parser",
        entries=[
            ConfigEntry(
                name="PARSER_LAZY",
                default=False,
                required=False, internal=False,
                description="Do not enforce some parser policies."),
            ConfigEntry(
                name="FUZZY_MIN_SCORE",
                default=90,
                required=False, internal=False,
                description="Todos with at least this equality score are "
                            "considered equal whe importing old protocols."),
            ConfigEntry(
                name="PRIVATE_KEYWORDS",
                default=["private", "internal", "privat", "intern"],
                required=False, internal=False,
                description="Keywords indicating private protocol parts"),
        ],
        check=check_parser,
        description="Settings for the protocol syntax parser"),
    ConfigSection(
        name="Rendering",
        entries=[
            ConfigEntry(
                name="FONTS",
                default={
                    "main": {
                        "extension": ".otf",
                        "path": "/usr/share/fonts/gsfonts/",
                        "regular": "NimbusSans-Regular",
                        "bold": "NimbusSans-Bold",
                        "italic": "NimbusSans-Italic",
                        "bolditalic": "NimbusSans-BoldItalic"
                    },
                    "roman": {
                        "extension": ".otf",
                        "path": "/usr/share/fonts/gsfonts/",
                        "regular": "NimbusRoman-Regular",
                        "bold": "NimbusRoman-Bold",
                        "italic": "NimbusRoman-Italic",
                        "bolditalic": "NimbusRoman-BoldItalic"
                    },
                    "sans": {
                        "extension": ".otf",
                        "path": "/usr/share/fonts/gsfonts/",
                        "regular": "NimbusSans-Regular",
                        "bold": "NimbusSans-Bold",
                        "italic": "NimbusSans-Italic",
                        "bolditalic": "NimbusSans-BoldItalic"
                    },
                    "mono": {
                        "extension": ".otf",
                        "path": "/usr/share/fonts/gsfonts/",
                        "regular": "NimbusMonoPS-Regular",
                        "bold": "NimbusMonoPS-Bold",
                        "italic": "NimbusMonoPS-Italic",
                        "bolditalic": "NimbusMonoPS-BoldItalic"
                    }
                },
                required=True, internal=False,
                description="fonts for xelatex"),
            ConfigEntry(
                name="DOCUMENTS_PATH",
                default="documents",
                required=False, internal=True,
                description="Path to the directory to save protocols in. "
                            "Write access is necessary."),
            ConfigEntry(
                name="LATEX_BULLETPOINTS",
                default=[
                    r"\textbullet", r"\normalfont \bfseries \textendash",
                    r"\textasteriskcentered", r"\textperiodcentered"],
                required=False, internal=False,
                description="list of bulletpoints to use in latex"),
            ConfigEntry(
                name="HTML_LEVEL_OFFSET",
                default=3,
                required=False, internal=False,
                description="Header level at which to start with "
                            "HTML headlines"),
            ConfigEntry(
                name="LATEX_LOCAL_TEMPLATES",
                default=None,
                required=False, internal=False,
                description="path to additional jinja2 templates"),
            ConfigEntry(
                name="LATEX_LOGO_TEMPLATE",
                default=None,
                required=False, internal=False,
                description="template to include at the top of protocols"),
            ConfigEntry(
                name="LATEX_GEOMETRY",
                default="vmargin=1.5cm,hmargin={1.5cm,1.2cm},"
                        "bindingoffset=8mm",
                required=False, internal=False,
                description="custom latex page geometry"),
            ConfigEntry(
                name="LATEX_PAGESTYLE",
                default=None,
                required=False, internal=False,
                description="custom latex pagestyle, e.g. 'fancy'"),
            ConfigEntry(
                name="LATEX_HEADER_FOOTER",
                default=False,
                required=False, internal=False,
                description="Include a header and footer in protocols"),
            ConfigEntry(
                name="LATEX_ADDITIONAL_PACKAGES",
                default=None,
                required=False, internal=False,
                description="Include additional latex packages in protocols"),
            ConfigEntry(
                name="LATEX_TEMPLATES",
                default=None,
                required=False, internal=False,
                description=(
                    "define multiple LaTeX-templates to use with a each "
                    "protocol type individually overriding the general LATEX "
                    "options the LATEX_LOCAL_TEMPLATES parameter is need to "
                    "provide the path for the templates each template must "
                    "be placed in an individual folder named by its ID in "
                    "LATEX_TEMPLATES and must contain the provided template "
                    "files: e.g. the files for the template 'yourtemplate' "
                    "need to be in the folder named 'yourtemplate', and the "
                    "templates provides the files: 'protokoll2.cls' (class), "
                    "'protocol.tex' (protocol), 'decision.tex' (decision) and "
                    "'asta-logo.tex'")),
        ],
        check=check_rendering,
        description="Settings for rendering protocols to pdf, html, etc."),
    ConfigSection(
        name="MAIL",
        entries=[
            ConfigEntry(
                name="MAIL_FROM",
                default="protokolle@example.com",
                required=True, internal=False, no_sane_default=True,
                description="Mail sender address"),
            ConfigEntry(
                name="MAIL_HOST",
                default="mail.example.com:465",
                required=True, internal=True, no_sane_default=True,
                description="SMTP Mail server address with port"),
            ConfigEntry(
                name="MAIL_USER",
                default="",
                required=False, internal=True,
                description="Mail server login user. "
                            "Empty for no authentication."),
            ConfigEntry(
                name="MAIL_PASSWORD",
                default="",
                required=False, internal=True,
                description="Mail server login password. "
                            "Empty for no authentication."),
            ConfigEntry(
                name="MAIL_USE_TLS",
                default=True,
                required=False, internal=True,
                description="Use SMPTS (not STARTTLS). Should match port."),
            ConfigEntry(
                name="MAIL_USE_STARTTLS",
                default=False,
                required=False, internal=True,
                description="Use SMTP with STARTTLS. Should match port."),

        ],
        check=check_mail,
        deactivatable=True,
        description="Mail server connection"),
    ConfigSection(
        name="PRINTING",
        entries=[
            ConfigEntry(
                name="PRINTING_SERVER",
                default="printsrv.example.com:631",
                required=True, internal=True, no_sane_default=True,
                description="CUPS printserver connection"),
            ConfigEntry(
                name="PRINTING_USER",
                default="protocols",
                required=False, internal=True,
                description="CUPS user for print jobs"),
            ConfigEntry(
                name="PRINTING_PRINTERS",
                default={
                    "example_printer":
                        ["Duplex=DuplexNoTumble", "option2=value"],
                    "other_printer": ["list", "of", "options"],
                },
                required=True, internal=False, no_sane_default=True,
                description="printers with corresponding options"),
        ],
        check=check_printing,
        deactivatable=True,
        description="CUPS printing settings"),
    ConfigSection(
        name="ETHERPAD",
        entries=[
            ConfigEntry(
                name="ETHERPAD_URL",
                default="https://example.com/etherpad",
                required=True, internal=False, no_sane_default=True,
                description=(
                    "URL of the etherpad installation. "
                    "Do not include the '/p'!")),
            ConfigEntry(
                name="ETHERPAD_API_URL",
                default="https://example.com/etherpad/api",
                required=False, internal=True, no_sane_default=True,
                description=("URL of the etherpad API. "
                             "Usually ETHERPAD_URL + /api")),
            ConfigEntry(
                name="ETHERPAD_APIKEY",
                default="abc123",
                required=True, internal=True, no_sane_default=True,
                description="Key to access the etherpad API"),
            ConfigEntry(
                name="EMPTY_ETHERPAD",
                default="\n".join([
                    "Welcome to Etherpad!",
                    "",
                    "This pad text is synchronized as you type, so that "
                    "everyone viewing this page sees the same text. This "
                    "allows you to collaborate seamlessly on documents!",
                    "",
                    "Get involved with Etherpad at http://etherpad.org",
                    ""
                ]),
                required=False, internal=False,
                description="The content a new etherpad contains."),
        ],
        check=check_etherpad,
        deactivatable=True,
        description="Etherpad settings"),
    ConfigSection(
        name="WIKI",
        entries=[
            ConfigEntry(
                name="WIKI_TYPE",
                default="MEDIAWIKI",
                required=True, internal=False,
                description="'MEDIAWIKI' or 'DOKUWIKI'"),
            ConfigEntry(
                name="WIKI_API_URL",
                default="https://wiki.example.com/wiki/api.php",
                required=True, internal=True, no_sane_default=True,
                description=(
                    "API Endpoint for Mediawiki, "
                    "'https://user:password@wiki.example.com/lib/exe/"
                    "xmlrpc.php' for Dokuwiki")),
            ConfigEntry(
                name="WIKI_ANONYMOUS",
                default=False,
                required=False, internal=True,
                description="Skip login (only for Mediawiki)"),
            ConfigEntry(
                name="WIKI_USER",
                default=None,
                required=False, internal=True,
                description="Login user (only for Mediawiki)"),
            ConfigEntry(
                name="WIKI_PASSWORD",
                default=None,
                required=False, internal=True,
                description="Login password (only for Mediawiki)"),
            ConfigEntry(
                name="WIKI_DOMAIN",
                default=None,
                required=False, internal=True,
                description="Login domain (only for Mediawiki)"),
        ],
        check=check_wiki,
        deactivatable=True,
        description="Mediawiki or Dokuwiki settings"),
    ConfigSection(
        name="CALENDAR",
        entries=[
            ConfigEntry(
                name="CALENDAR_URL",
                default="https://user:password@calendar.example.com/dav/",
                required=True, internal=True, no_sane_default=True,
                description="CalDAV server URL"),
            ConfigEntry(
                name="CALENDAR_DEFAULT_DURATION",
                default=3,
                required=False, internal=False,
                description="Default meeting length in hours"),
            ConfigEntry(
                name="CALENDAR_MAX_REQUESTS",
                default=10,
                required=False, internal=False,
                description=(
                    "Number of retries before giving a connection attempt up. "
                    "Some CalDAV servers reply randomly with errors.")),
        ],
        check=check_calendar,
        deactivatable=True,
        description="CalDAV settings"),
    ConfigSection(
        name="TIMEZONE",
        entries=[
            ConfigEntry(
                name="CALENDAR_TIMEZONE_MAP",
                default={
                    "CET": "Europe/Berlin",
                    "CEST": "Europe/Berline",
                },
                required=False, internal=False,
                description="Timezone abbreviation map. Add as needed."),
        ],
        check=check_timezone,
        description="Settings for translating timezone information."),
]


class Config:
    def __init__(self, data=None):
        if data is None:
            data = {}
        object.__setattr__(self, "data", data)

    def __setattr__(self, key, value):
        self.data[key] = value

    def __getattr__(self, key):
        try:
            return self.data[key]
        except KeyError:
            raise AttributeError

    def __dir__(self):
        return self.data.keys()


def import_config(sections=CONFIG_SECTIONS):
    import config
    for section in sections:
        section.extract(config)
    internal_config, public_config = Config(), Config()
    for section in sections:
        section.fill_modules(internal_config, public_config)
    return internal_config, public_config


def check_config(sections=CONFIG_SECTIONS):
    import config
    successful = True
    for section in sections:
        section.extract(config)
        if not section.deactivatable or section.active:
            logger.info("Checking {}".format(section.name))
            try:
                section.check(
                    **{entry.name: entry.value for entry in section.entries})
            except ValueError as error:
                logger.error(error.args[0])
                successful = False
    return successful


def write_example_config(
        sections=CONFIG_SECTIONS, filename="config.py.example"):
    example_config = "\n".join([
        section.get_example()
        for section in sections
    ])
    with open(filename, "w") as example_config_file:
        example_config_file.write(example_config)


if __name__ == "__main__":
    import argparse
    import sys
    parser = argparse.ArgumentParser(
        description="Create and check the config")
    subparsers = parser.add_subparsers(dest="command")
    subparsers.required = True

    check_parser = subparsers.add_parser("check")
    check_parser.add_argument(
        "--log-level", choices=["error", "warning", "info", "debug"])

    create_parser = subparsers.add_parser("create")
    create_parser.add_argument("--filename", default="config.py.example")

    show_parser = subparsers.add_parser("show")

    arguments = parser.parse_args()

    if arguments.command == "check":
        if arguments.log_level:
            logger.setLevel(arguments.log_level.upper())
        sys.exit(not check_config())
    elif arguments.command == "create":
        filename = arguments.filename
        write_example_config(filename=filename)
        print("An example config has been generated at {}. "
              "Please change the requried entries.".format(filename))
    elif arguments.command == "show":
        import pprint
        internal_config, public_config = import_config()
        print("The complete config is:")
        pprint.pprint(internal_config.data)
        print("The public part is:")
        pprint.pprint(public_config.data)
