from flask_sqlalchemy import SQLAlchemy

import re

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
    #('[', '\\['),
    #(']', '\\]'),
    #('"', '"\''),
    ('~', '$\\sim{}$'),
    ('^', '\\textasciicircum{}'),
    ('Ë„', '\\textasciicircum{}'),
    ('`', '{}`'),
    ('-->', '$\longrightarrow$'),
    ('->', '$\rightarrow$'),
    ('==>', '$\Longrightarrow$'),
    ('=>', '$\Rightarrow$'),
    ('>=', '$\geq$'),
    ('=<', '$\leq$'),
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
def time_filter(time):
    return time.strftime("%H:%m")

def class_filter(obj):
    return obj.__class__.__name__

from auth import LdapManager, SecurityManager
ldap_manager = LdapManager(config.LDAP_PROVIDER_URL, config.LDAP_BASE)
security_manager = SecurityManager(config.SECURITY_KEY)
