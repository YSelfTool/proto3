from flask import request, flash, abort

from functools import wraps
from hmac import compare_digest

from models.database import ALL_MODELS
from shared import current_user
from utils import get_csrf_token
from common import back

ID_KEY = "id"
KEY_NOT_PRESENT_MESSAGE = "Missing {}_id."
OBJECT_DOES_NOT_EXIST_MESSAGE = "There is no {} with id {}."

MISSING_VIEW_RIGHT = "Dir fehlenden die nötigen Zugriffsrechte."


def default_redirect():
    return back.redirect()


def login_redirect():
    return back.redirect("login")


def db_lookup(*models, check_exists=True):
    def _decorator(function):
        @wraps(function)
        def _decorated_function(*args, **kwargs):
            for model in models:
                key = model.__model_name__
                id_key = "{}_{}".format(key, ID_KEY)
                if id_key not in kwargs:
                    flash(KEY_NOT_PRESENT_MESSAGE.format(key), "alert-error")
                    return default_redirect()
                obj_id = kwargs[id_key]
                obj = model.query.filter_by(id=obj_id).first()
                if check_exists and obj is None:
                    model_name = model.__class__.__name__
                    flash(OBJECT_DOES_NOT_EXIST_MESSAGE.format(
                        model_name, obj_id),
                        "alert-error")
                    return default_redirect()
                kwargs[key] = obj
                kwargs.pop(id_key)
            return function(*args, **kwargs)
        return _decorated_function
    return _decorator


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


def protect_csrf(function):
    @wraps(function)
    def _decorated_function(*args, **kwargs):
        token = request.args.get("csrf_token")
        true_token = get_csrf_token()
        if token is None or not compare_digest(token, true_token):
            abort(400)
        return function(*args, **kwargs)
    return _decorated_function
