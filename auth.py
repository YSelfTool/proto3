import ldap
import hmac, hashlib

class User:
    def __init__(self, username, groups):
        self.username = username
        self.groups = groups

    def summarize(self):
        return "{}:{}".format(self.username, ",".join(self.groups))

    @staticmethod
    def from_summary(summary):
        name, groupstring = summary.split(":", 1)
        groups = groupstring.split(",")
        return User(name, groups)

    @staticmethod
    def from_hashstring(secure_string):
        summary, hash = secure_string.split("=", 1)
        return User.from_summary(summary)

class LdapManager:
    def __init__(self, url, base):
        self.connection = ldap.initialize(url)
        self.base = base

    def login(self, username, password):
        if not self.authenticate(username, password):
            return None
        groups = list(map(lambda g: g.decode("utf-8"), self.groups(username)))
        print(groups)
        return User(username, groups)

    def authenticate(self, username, password):
        try:
            self.connection.simple_bind_s("uid={},ou=users,{}".format(username, self.base), password)
            return True
        except ldap.INVALID_CREDENTIALS:
            return False
        return False

    def groups(self, username):
        result = []
        for _, result_dict in self.connection.search_s(self.base, ldap.SCOPE_SUBTREE, "(memberUid={})".format(username), ["cn"]):
            result.append(result_dict["cn"][0])
        return result

class SecurityManager:
    def __init__(self, key):
        self.maccer = hmac.new(key.encode("utf-8"), digestmod=hashlib.sha512)

    def hash_user(self, user):
        maccer = self.maccer.copy()
        summary = user.summarize()
        maccer.update(summary.encode("utf-8"))
        return "{}={}".format(summary, maccer.hexdigest())

    def check_user(self, string):
        parts = string.split("=", 1)
        if len(parts) != 2:
            # wrong format, expecting summary:hash
            return False
        summary, hash = map(lambda s: s.encode("utf-8"), parts)
        maccer = self.maccer.copy()
        maccer.update(summary)
        return hmac.compare_digest(maccer.hexdigest().encode("utf-8"), hash)
