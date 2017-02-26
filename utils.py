from flask import render_template, request

import random
import string
import regex
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from datetime import datetime, date, timedelta
import requests
from io import BytesIO

import config

def random_string(length):
    return "".join((random.choice(string.ascii_letters) for i in range(length)))

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
        

class UrlManager:
    def __init__(self, config):
        self.pattern = regex.compile(r"(?:(?<proto>https?):\/\/)?(?<hostname>[[:alnum:]_.]+(?:\:[[:digit:]]+)?)?(?<path>(?:\/[[:alnum:]_#]*)+)?(?:\?(?<params>.*))?")
        self.base = "{}://{}{}{}"
        self.proto = getattr(config, "URL_PROTO", "https")
        self.root = getattr(config, "URL_ROOT", "example.com")
        self.path = getattr(config, "URL_PATH", "/")
        self.params = getattr(config, "URL_PARAMS", "")

    def complete(self, url):
        match = self.pattern.match(url)
        if match is None:
            return None
        proto = match.group("proto") or self.proto
        root = match.group("hostname") or self.root
        path = match.group("path") or self.path
        params = match.group("params") or self.params
        return self.base.format(proto, root, path, "?" + params if len(params) > 0 else "")

url_manager = UrlManager(config)

class MailManager:
    def __init__(self, config):
        self.active = getattr(config, "MAIL_ACTIVE", False)
        self.from_addr = getattr(config, "MAIL_FROM", "")
        self.hostname = getattr(config, "MAIL_HOST", "")
        self.username = getattr(config, "MAIL_USER", "")
        self.password = getattr(config, "MAIL_PASSWORD", "")

    def send(self, to_addr, subject, content, appendix=None):
        if (not self.active
            or not self.hostname
            or not self.username
            or not self.password
            or not self.from_addr):
            return
        msg = MIMEMultipart("mixed") # todo: test if clients accept attachment-free mails set to multipart/mixed
        msg["From"] = self.from_addr
        msg["To"] = to_addr
        msg["Subject"] = subject
        msg.attach(MIMEText(content, _charset="utf-8"))
        if appendix is not None:
            for name, file_like in appendix:
                part = MIMEApplication(file_like.read(), "octet-stream")
                part["Content-Disposition"] = 'attachment; filename="{}"'.format(name)
                msg.attach(part)
        server = smtplib.SMTP_SSL(self.hostname)
        server.login(self.username, self.password)
        server.sendmail(self.from_addr, to_addr, msg.as_string())
        server.quit()

mail_manager = MailManager(config)

def get_first_unused_int(numbers):
    positive_numbers = [number for number in numbers if number >= 0]
    if len(positive_numbers) == 0:
        return 0
    highest = max(positive_numbers)
    for given, linear in zip(positive_numbers, range(highest+1)):
        if linear < given:
            return linear
    return highest + 1

def get_etherpad_url(pad):
    return "{}/p/{}".format(config.ETHERPAD_URL, pad)
def get_etherpad_export_url(pad):
    return "{}/p/{}/export/txt".format(config.ETHERPAD_URL, pad)
def get_etherpad_import_url(pad):
    return "{}/p/{}/import".format(config.ETHERPAD_URL, pad)

def get_etherpad_text(pad):
    req = requests.get("{}/p/{}/export/txt".format(config.ETHERPAD_URL, pad))
    return req.text

def set_etherpad_text(pad, text, only_if_default=True):
    if only_if_default:
        current_text = get_etherpad_text(pad)
        if current_text != config.EMPTY_ETHERPAD and len(current_text.strip()) > 0:
            return False
    file_like = BytesIO(text.encode("utf-8"))
    files = {"file": file_like}
    req = requests.post(get_etherpad_import_url(pad), files=files)
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
