from flask import redirect, flash, request

from functools import wraps

ID_KEY = "id"
KEY_NOT_PRESENT_MESSAGE = "Missing {}_id."
OBJECT_DOES_NOT_EXIST_MESSAGE = "There is no {} with id {}."

def default_redirect():
    return redirect(request.args.get("next") or url_for("index"))

def db_lookup(*models, check_exists=True):
    def _decorator(function):
        @wraps(function)
        def _decorated_function(*args, **kwargs):
            for model in models:
                key = model.__object_name__
                id_key = "{}_{}".format(key, ID_KEY)
                if id_key not in kwargs:
                    flash(KEY_NOT_PRESENT_MESSAGE.format(key), "alert-error")
                    return default_redirect()
                obj_id = kwargs[id_key]
                obj = model.query.filter_by(id=obj_id).first()
                if check_exists and obj is None:
                    model_name = model.__class__.__name__
                    flash(OBJECT_DOES_NOT_EXIST_MESSAGE.format(model_name, obj_id),
                        "alert-error")
                    return default_redirect()
                kwargs[key] = obj
                kwargs.pop(id_key)
            return function(*args, **kwargs)
        return _decorated_function
    return _decorator
