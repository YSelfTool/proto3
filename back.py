# This snippet is in public domain.
# However, please retain this link in your sources:
# http://flask.pocoo.org/snippets/120/
# Danya Alexeyevsky

import functools
from flask import session, request, redirect as flask_redirect, url_for
import config

cookie = getattr(config, "REDIRECT_BACK_COOKIE", "back")
default_view = getattr(config, "REDIRECT_BACK_DEFAULT", "index")


def anchor(func, cookie=cookie):
    @functools.wraps(func)
    def result(*args, **kwargs):
        session[cookie] = request.url
        return func(*args, **kwargs)
    return result


def url(default=default_view, cookie=cookie, **url_args):
    return session.get(cookie, url_for(default, **url_args))


def redirect(default=default_view, cookie=cookie, **url_args):
    return flask_redirect(url(default, cookie, **url_args))
