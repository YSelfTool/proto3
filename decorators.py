from functools import wraps

from flask import flash

from models.database import ALL_MODELS
from shared import current_user
from common import back


def default_redirect():
    return back.redirect()


def login_redirect():
    return back.redirect("login")


MISSING_VIEW_RIGHT = "Dir fehlenden die nötigen Zugriffsrechte."


def require_right(right, require_exist):
    necessary_right_name = "has_{}_right".format(right)

    def _decorator(function):
        @wraps(function)
        def _decorated_function(*args, **kwargs):
            user = current_user()
            for model in ALL_MODELS:
                model_name = model.__model_name__
                if model_name in kwargs:
                    model = kwargs[model_name]
                    if model is None:
                        if require_exist:
                            flash(MISSING_VIEW_RIGHT, "alert-error")
                            return login_redirect()
                        else:
                            continue
                    necessary_right = getattr(model, necessary_right_name)
                    if not necessary_right(user):
                        flash(MISSING_VIEW_RIGHT, "alert-error")
                        return login_redirect()
            return function(*args, **kwargs)
        return _decorated_function
    return _decorator


def require_public_view_right(require_exist=True):
    return require_right("public_view", require_exist)


def require_private_view_right(require_exist=True):
    return require_right("private_view", require_exist)


def require_modify_right(require_exist=True):
    return require_right("modify", require_exist)


def require_publish_right(require_exist=True):
    return require_right("publish", require_exist)


def require_admin_right(require_exist=True):
    return require_right("admin", require_exist)
