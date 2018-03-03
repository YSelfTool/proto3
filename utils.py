from flask import request

import random
import string
import math
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from datetime import datetime
import requests
from io import BytesIO
import ipaddress
from socket import getfqdn
from uuid import uuid4
import subprocess

import config


def random_string(length):
    return "".join((random.choice(string.ascii_letters)
                    for i in range(length)))


def is_past(some_date):
    return (datetime.now() - some_date).total_seconds() > 0


def encode_kwargs(kwargs):
    encoded_kwargs = {}
    for key in kwargs:
        value = kwargs[key]
        if hasattr(value, "id"):
            encoded_kwargs[key] = (type(value), value.id, True)
        else:
            encoded_kwargs[key] = (type(value), value, False)
    return encoded_kwargs


def decode_kwargs(encoded_kwargs):
    kwargs = {}
    for name in encoded_kwargs:
        kind, id, from_db = encoded_kwargs[name]
        if from_db:
            kwargs[name] = kind.query.filter_by(id=id).first()
        else:
            kwargs[name] = id
    return kwargs


class MailManager:
    def __init__(self, config):
        self.active = getattr(config, "MAIL_ACTIVE", False)
        self.from_addr = getattr(config, "MAIL_FROM", "")
        self.hostname = getattr(config, "MAIL_HOST", "")
        self.username = getattr(config, "MAIL_USER", "")
        self.password = getattr(config, "MAIL_PASSWORD", "")
        self.use_tls = getattr(config, "MAIL_USE_TLS", True)
        self.use_starttls = getattr(config, "MAIL_USE_STARTTLS", False)

    def _get_smtp(self):
        if self.use_tls:
            return smtplib.SMTP_SSL
        return smtplib.SMTP

    def send(self, to_addr, subject, content, appendix=None, reply_to=None):
        if (not self.active
                or not self.hostname
                or not self.from_addr):
            return
        msg = MIMEMultipart("mixed")
        msg["From"] = self.from_addr
        msg["To"] = to_addr
        msg["Subject"] = subject
        msg["Message-ID"] = "<{}@{}>".format(uuid4(), getfqdn())
        if reply_to is not None:
            msg["Reply-To"] = reply_to
        msg.attach(MIMEText(content, _charset="utf-8"))
        if appendix is not None:
            for name, file_like in appendix:
                part = MIMEApplication(file_like.read(), "octet-stream")
                part["Content-Disposition"] = (
                    'attachment; filename="{}"'.format(name))
                msg.attach(part)
        server = self._get_smtp()(self.hostname)
        if self.use_starttls:
            server.starttls()
        if self.username not in [None, ""] and self.password not in [None, ""]:
            server.login(self.username, self.password)
        server.sendmail(self.from_addr, to_addr.split(","), msg.as_string())
        server.quit()


mail_manager = MailManager(config)


def get_first_unused_int(numbers):
    positive_numbers = [number for number in numbers if number >= 0]
    if len(positive_numbers) == 0:
        return 0
    highest = max(positive_numbers)
    for given, linear in zip(positive_numbers, range(highest + 1)):
        if linear < given:
            return linear
    return highest + 1


def normalize_pad(pad):
    return pad.replace(" ", "_")


def get_etherpad_url(pad):
    return "{}/p/{}".format(config.ETHERPAD_URL, normalize_pad(pad))


def get_etherpad_export_url(pad):
    return "{}/p/{}/export/txt".format(config.ETHERPAD_URL, normalize_pad(pad))


def get_etherpad_import_url(pad):
    return "{}/p/{}/import".format(config.ETHERPAD_URL, normalize_pad(pad))


def get_etherpad_text(pad):
    req = requests.get(get_etherpad_export_url(pad))
    return req.text


def set_etherpad_text(pad, text, only_if_default=True):
    print(pad)
    if only_if_default:
        current_text = get_etherpad_text(pad)
        if (current_text != config.EMPTY_ETHERPAD
                and len(current_text.strip()) > 0):
            return False
    file_like = BytesIO(text.encode("utf-8"))
    files = {"file": file_like}
    url = get_etherpad_import_url(pad)
    print(url)
    req = requests.post(url, files=files)
    return req.status_code == 200


def split_terms(text, quote_chars="\"'", separators=" \t\n"):
    terms = []
    in_quote = False
    last_quote_char = ""
    current_term = ""
    for char in text:
        if in_quote:
            if char != last_quote_char:
                current_term += char
            else:
                in_quote = False
                last_quote_char = ""
                terms.append(current_term)
                current_term = ""
        else:
            if char in separators:
                if len(current_term) > 0:
                    terms.append(current_term)
                    current_term = ""
            else:
                if char in quote_chars and len(current_term) == 0:
                    in_quote = True
                    last_quote_char = char
                else:
                    current_term += char
    if len(current_term) > 0:
        terms.append(current_term)
    return terms


def optional_int_arg(name):
    try:
        return int(request.args.get(name))
    except (ValueError, TypeError):
        return None


def add_line_numbers(text):
    raw_lines = text.splitlines()
    linenumber_length = math.ceil(math.log10(len(raw_lines)) + 1)
    lines = []
    for linenumber, line in enumerate(raw_lines):
        lines.append("{} {}".format(
            str(linenumber + 1).rjust(linenumber_length),
            line
        ))
    return "\n".join(lines)


def check_ip_in_networks(networks_string):
    address = ipaddress.ip_address(request.remote_addr)
    if (address == ipaddress.ip_address("127.0.0.1")
            and "X-Real-Ip" in request.headers):
        address = ipaddress.ip_address(request.headers["X-Real-Ip"])
    try:
        for network_string in networks_string.split(","):
            network = ipaddress.ip_network(network_string.strip())
            if address in network:
                return True
        return False
    except ValueError:
        return False


def fancy_join(values, sep1=" und ", sep2=", "):
    values = list(values)
    if len(values) <= 1:
        return "".join(values)
    last = values[-1]
    start = values[:-1]
    return "{}{}{}".format(sep2.join(start), sep1, last)


def footnote_hash(text, length=5):
    return str(sum(ord(c) * i for i, c in enumerate(text)) % 10**length)


def parse_datetime_from_string(text):
    text = text.strip()
    for format in ("%d.%m.%Y", "%d.%m.%y", "%Y-%m-%d",
                   "%d. %B %Y", "%d. %b %Y", "%d. %B %y", "%d. %b %y"):
        try:
            return datetime.strptime(text, format)
        except ValueError:
            pass
    for format in ("%d.%m.", "%d. %m.", "%d.%m", "%d.%m"):
        try:
            return datetime.strptime(text, format).replace(
                year=datetime.now().year)
        except ValueError:
            pass
    raise ValueError("Date '{}' does not match any known format!".format(text))


def get_git_revision():
    try:
        gitlab_url = "https://git.fsmpi.rwth-aachen.de/protokollsystem/proto3"
        commit_hash = subprocess.check_output(
            ["git", "log", "-g", "-1", "--pretty=%H"]).decode("UTF-8").strip()
        timestamp = int(subprocess.check_output(
            ["git", "log", "-g", "-1", "--pretty=%at"]).strip())
        commit_date = datetime.fromtimestamp(timestamp)
        return {"url": gitlab_url, "hash": commit_hash, "date": commit_date}
    except subprocess.SubprocessError:
        pass


def get_max_page_length_exp(objects):
    length = len(objects)
    if length > 0:
        return math.ceil(math.log10(length))
    return 1


def get_internal_filename(protocol, document, filename):
    return "{}-{}-{}".format(protocol.id, document.id, filename)
