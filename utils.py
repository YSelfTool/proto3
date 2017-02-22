from flask import render_template

import random
import string
import regex
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime, date, timedelta

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
        self.prefix = getattr(config, "MAIL_PREFIX", "")

    def send(self, to_addr, subject, content):
        if (not self.active
            or not self.hostname
            or not self.username
            or not self.password
            or not self.from_addr):
            return True
        try:
            msg = MIMEMultipart("alternative")
            msg["From"] = self.from_addr
            msg["To"] = to_addr
            msg["Subject"] = "[{}] {}".format(self.prefix, subject) if self.prefix else subject
            msg.attach(MIMEText(content, _charset="utf-8"))
            server = smtplib.SMTP_SSL(self.hostname)
            server.login(self.username, self.password)
            server.sendmail(self.from_addr, to_addr, msg.as_string())
            server.quit()
        except Exception as e:
            print(e)
            return False
        return True

mail_manager = MailManager(config)
