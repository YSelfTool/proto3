import requests
import json

import config

HTTP_STATUS_OK = 200

class WikiException(Exception):
    pass

def _filter_params(params):
    result = {}
    for key, value in sorted(params.items(), key=lambda t: t[0] == "token"):
        if isinstance(value, bool):
            if value:
                result[key] = ""
        else:
            result[key] = value
    return result

class WikiClient:
    def __init__(self, active=None, endpoint=None, anonymous=None,  user=None, password=None, domain=None):
        self.active = active if active is not None else config.WIKI_ACTIVE
        self.endpoint = endpoint if endpoint is not None else config.WIKI_API_URL
        self.anonymous = anonymous if anonymous is not None else config.WIKI_ANONYMOUS
        self.user = user if user is not None else config.WIKI_USER
        self.password = password if password is not None else config.WIKI_PASSWORD
        self.domain = domain if domain is not None else config.WIKI_DOMAIN
        self.token = None
        self.cookies = requests.cookies.RequestsCookieJar()

    def __enter__(self):
        if not self.anonymous:
            self.login()
        return self

    def __exit__(self, type, value, traceback):
        if not self.anonymous:
            self.logout()

    def is_logged_in(self):
        return self.token is not None

    def login(self):
        if not self.active:
            return
        # todo: Change this to the new MediaWiki tokens api once the wiki is updated
        token_answer = self.do_action("login", method="post", lgname=self.user)
        if "login" not in token_answer or "token" not in token_answer["login"]:
            raise WikiException("No token in login answer.")
        lgtoken = token_answer["login"]["token"]
        login_answer = self.do_action("login", method="post", lgname=self.user, lgpassword=self.password, lgdomain=self.domain, lgtoken=lgtoken)
        if ("login" not in login_answer
        or "result" not in login_answer["login"]
        or login_answer["login"]["result"] != "Success"):
            raise WikiException("Login not successful.")


    def logout(self):
        if not self.active:
            return
        self.do_action("logout")

    def edit_page(self, title, content, summary, recreate=True, createonly=False):
        if not self.active:
            return
        # todo: port to new api once the wiki is updated
        prop_answer = self.do_action("query", method="get", prop="info", intoken="edit", titles=title)
        if ("query" not in prop_answer
        or "pages" not in prop_answer["query"]):
            raise WikiException("Can't get token for page {}".format(title))
        pages = prop_answer["query"]["pages"]
        edit_token = None
        for page in pages.values():
            if page["title"] == title:
                edit_token = page["edittoken"]
                break
        if edit_token is None:
            raise WikiException("Can't get token for page {}".format(title))
        edit_answer = self.do_action(action="edit", method="post", data={"text": content},
            token=edit_token, title=title,
            summary=summary, recreate=recreate,
            createonly=createonly, bot=True)

    def do_action(self, action, method="get", data=None, **kwargs):
        if not self.active:
            return
        kwargs["action"] = action
        kwargs["format"] = "json"
        params = _filter_params(kwargs)
        req = None
        if method == "get":
            req = requests.get(self.endpoint, cookies=self.cookies, params=params)
        elif method == "post":
            req = requests.post(self.endpoint, cookies=self.cookies, data=data, params=params)
        if req.status_code != HTTP_STATUS_OK:
            raise WikiException("HTTP status code {} on action {}.".format(req.status_code, action))
        self.cookies = req.cookies
        return req.json()

def main():
    with WikiClient() as client:
        client.edit_page(title="Test", content="This is a very long text.", summary="API client test")

