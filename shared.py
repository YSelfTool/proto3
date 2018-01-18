from flask_sqlalchemy import SQLAlchemy
from flask import session, redirect, url_for, request

import re
from functools import wraps
from enum import Enum

import config

db = SQLAlchemy()

# the following code is written by Lars Beckers and not to be published without permission
latex_chars = [
    ("\\", "\\backslash"), # this needs to be first
    ("$", "\$"),
    ('%', '\\%'),
    ('&', '\\&'),
    ('#', '\\#'),
    ('_', '\\_'),
    ('{', '\\{'),
    ('}', '\\}'),
    ('[', '\\['),
    (']', '\\]'),
    #('"', '"\''),
    ('~', r'$\sim{}$'),
    ('^', r'\textasciicircum{}'),
    ('Ë„', r'\textasciicircum{}'),
    ('`', '{}`'),
    ('-->', r'$\longrightarrow$'),
    ('->', r'$\rightarrow$'),
    ('==>', r'$\Longrightarrow$'),
    ('=>', r'$\Rightarrow$'),
    ('>=', r'$\geq$'),
    ('=<', r'$\leq$'),
    ('<', '$<$'),
    ('>', '$>$'),
    ('\\backslashin', '$\\in$'),
    ('\\backslash', '$\\backslash$') # this needs to be last
]

def escape_tex(text):
    out = text
    for old, new in latex_chars:
        out = out.replace(old, new)
    # beware, the following is carefully crafted code
    res = ''
    k, l = (0, -1)
    while k >= 0:
        k = out.find('"', l+1)
        if k >= 0:
            res += out[l+1:k]
            l = out.find('"', k+1)
            if l >= 0:
                res += '\\enquote{' + out[k+1:l] + '}'
            else:
                res += '"\'' + out[k+1:]
            k = l
        else:
            res += out[l+1:]
    # yes, this is not quite escaping latex chars, but anyway...
    res = re.sub('([a-z])\(', '\\1 (', res)
    res = re.sub('\)([a-z])', ') \\1', res)
    #logging.debug('escape latex ({0}/{1}): {2} --> {3}'.format(len(text), len(res), text.split('\n')[0], res.split('\n')[0]))
    return res

def unhyphen(text):
    return " ".join([r"\mbox{" + word + "}" for word in text.split(" ")])

def date_filter(date):
    return date.strftime("%d. %B %Y")
def datetime_filter(date):
    return date.strftime("%d. %B %Y, %H:%M")
def date_filter_long(date):
    return date.strftime("%A, %d.%m.%Y, Kalenderwoche %W")
def date_filter_short(date):
    return date.strftime("%d.%m.%Y")
def time_filter(time):
    return time.strftime("%H:%M Uhr")
def time_filter_short(time):
    return time.strftime("%H:%M")

def needs_date_test(todostate):
    return todostate.needs_date()
def todostate_name_filter(todostate):
    return todostate.get_name()

def indent_tab_filter(text):
    return "\n".join(map(lambda l: "\t{}".format(l), text.splitlines()))

def class_filter(obj):
    return obj.__class__.__name__
def code_filter(text):
    return "<code>{}</code>".format(text)

from auth import UserManager, SecurityManager, User
max_duration = getattr(config, "AUTH_MAX_DURATION")
user_manager = UserManager(backends=config.AUTH_BACKENDS)
security_manager = SecurityManager(config.SECURITY_KEY, max_duration)

def check_login():
    return "auth" in session and security_manager.check_user(session["auth"])
def current_user():
    if not check_login():
        return None
    return User.from_hashstring(session["auth"])

def login_required(function):
    @wraps(function)
    def decorated_function(*args, **kwargs):
        if check_login():
            return function(*args, **kwargs)
        else:
            return redirect(url_for("login", next=request.url))
    return decorated_function

def group_required(group):
    def decorator(function):
        @wraps(function)
        def decorated_function(*args, **kwargs):
            if group in current_user().groups:
                return function(*args, **kwargs)
            else:
                flash("You do not have the necessary permissions to view this page.")
                return redirect(request.args.get("next") or url_for("index"))
        return decorated_function
    return decorator

DATE_KEY = "Datum"
START_TIME_KEY = "Beginn"
END_TIME_KEY = "Ende"
KNOWN_KEYS = [DATE_KEY, START_TIME_KEY, END_TIME_KEY]

class WikiType(Enum):
    MEDIAWIKI = 0
    DOKUWIKI = 1
