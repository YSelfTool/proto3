import ldap
import hmac, hashlib
import ldap3
from ldap3.utils.dn import parse_dn
from datetime import datetime

class User:
    def __init__(self, username, groups, timestamp=None):
        self.username = username
        self.groups = groups
        if timestamp is not None:
            self.timestamp = timestamp
        else:
            self.timestamp = datetime.now()

    def summarize(self):
        return "{}:{}:{}".format(self.username, ",".join(self.groups), str(self.timestamp.timestamp()))

    @staticmethod
    def from_summary(summary):
        parts = summary.split(":", 2)
        if len(parts) != 3:
            return None
        name, groupstring, timestamp = parts
        groups = groupstring.split(",")
        return User(name, groups, datetime.fromtimestamp(float(timestamp)))

    @staticmethod
    def from_hashstring(secure_string):
        summary, hash = secure_string.split("=", 1)
        return User.from_summary(summary)

class UserManager:
    def __init__(self, backends):
        self.backends = backends

    def login(self, username, password):
        for backend in self.backends:
            if backend.authenticate(username, password):
                groups = backend.groups(username, password)
                return User(username, groups)
        return None

    def all_groups(self):
        for backend in self.backends:
            yield from backend.all_groups()

class LegacyLdapManager:
    def __init__(self, url, base):
        self.connection = ldap.initialize(url)
        self.base = base

    def login(self, username, password):
        if not self.authenticate(username, password):
            return None
        groups = list(map(lambda g: g.decode("utf-8"), self.groups(username)))
        return User(username, groups)

    def authenticate(self, username, password):
        try:
            self.connection.simple_bind_s("uid={},ou=users,{}".format(username, self.base), password)
            return True
        except ldap.INVALID_CREDENTIALS:
            return False
        return False

    def groups(self, username, password=None):
        result = []
        # use username.lower() since memberUid is case sensitive here
        for _, result_dict in self.connection.search_s(self.base, ldap.SCOPE_SUBTREE, "(memberUid={})".format(username.lower()), ["cn"]):
            result.append(result_dict["cn"][0])
        return result


class LdapManager:
    def __init__(self, host, user_dn, group_dn, port=636, use_ssl=True):
        self.server = ldap3.Server(host, port=port, use_ssl=use_ssl)
        self.user_dn = user_dn
        self.group_dn = group_dn

    def authenticate(self, username, password):
        connection = ldap3.Connection(self.server, self.user_dn.format(username), password)
        return connection.bind()

    def groups(self, username, password=None):
        connection = ldap3.Connection(self.server)
        obj_def = ldap3.ObjectDef("posixgroup", connection)
        group_reader = ldap3.Reader(connection, obj_def, self.group_dn)
        for group in group_reader.search():
            members = group.memberUid.value
            if members is not None and username in members:
                yield group.cn.value

    def all_groups(self):
        connection = ldap3.Connection(self.server)
        obj_def = ldap3.ObjectDef("posixgroup", connection)
        group_reader = ldap3.Reader(connection, obj_def, self.group_dn)
        for group in group_reader.search():
            yield group.cn.value

class ADManager:
    def __init__(self, host, domain, user_dn, group_dn, port=636, use_ssl=True):
        self.server = ldap3.Server(host, port=port, use_ssl=use_ssl)
        self.domain = domain
        self.user_dn = user_dn
        self.group_dn = group_dn

    def prepare_connection(self, username=None, password=None):
        if username is not None and password is not None:
            ad_user = "{}\\{}".format(self.domain, username)
            return ldap3.Connection(self.server, ad_user, password)
        return ldap3.Connection(self.server)
        
    def authenticate(self, username, password):
        return self.prepare_connection(username, password).bind()

    def groups(self, username, password):
        connection = self.prepare_connection(username, password)
        connection.bind()
        obj_def = ldap3.ObjectDef("user", connection)
        name_filter = "cn:={}".format(username)
        user_reader = ldap3.Reader(connection, obj_def, self.user_dn, name_filter)
        for result in user_reader.search():
            for group_dn in result.memberOf:
                group_dn_parts = parse_dn(group_dn)
                if len(group_dn_parts) >= 1:
                    for group_dn in group_dn_parts:
                        key, group, next_char = group_dn
                        yield group

    def all_groups(self):
        connection = self.prepare_connection()
        connection.bind()
        obj_def = ldap3.ObjectDef("group", connection)
        group_reader = ldap3.Reader(connection, obj_def, self.group_dn)
        for result in reader.search():
            yield result.name.value

class SecurityManager:
    def __init__(self, key, max_duration=300):
        self.maccer = hmac.new(key.encode("utf-8"), digestmod=hashlib.sha512)
        self.max_duration = max_duration

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
        session_duration = datetime.now() - User.from_hashstring(string).timestamp
        macs_equal = hmac.compare_digest(maccer.hexdigest().encode("utf-8"), hash)
        time_short = int(session_duration.total_seconds()) < self.max_duration 
        return macs_equal and time_short

