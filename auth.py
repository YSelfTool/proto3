import ldap
import hmac, hashlib
import ssl
import ldap3
from ldap3.utils.dn import parse_dn
from datetime import datetime

class User:
    def __init__(self, username, groups, timestamp=None, obsolete=False):
        self.username = username
        self.groups = groups
        if timestamp is not None:
            self.timestamp = timestamp
        else:
            self.timestamp = datetime.now()
        self.obsolete = obsolete

    def summarize(self):
        return "{}:{}:{}:{}".format(self.username, ",".join(self.groups), str(self.timestamp.timestamp()), self.obsolete)

    @staticmethod
    def from_summary(summary):
        parts = summary.split(":", 3)
        if len(parts) != 4:
            return None
        name, group_str, timestamp_str, obsolete_str = parts
        timestamp = datetime.fromtimestamp(float(timestamp_str))
        obsolete = obsolete_str == "True"
        groups = group_str.split(",")
        return User(name, groups, timestamp, obsolete)

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
                return User(username, groups, obsolete=backend.obsolete)
        return None

    def all_groups(self):
        for backend in self.backends:
            yield from backend.all_groups()


class LdapManager:
    def __init__(self, host, user_dn, group_dn, port=636, use_ssl=True, obsolete=False):
        self.server = ldap3.Server(host, port=port, use_ssl=use_ssl)
        self.user_dn = user_dn
        self.group_dn = group_dn
        self.obsolete = obsolete

    def authenticate(self, username, password):
        try:
            connection = ldap3.Connection(self.server, self.user_dn.format(username), password)
            return connection.bind()
        except ldap3.core.exceptions.LDAPSocketOpenError:
            return False

    def groups(self, username, password=None):
        connection = ldap3.Connection(self.server)
        obj_def = ldap3.ObjectDef("posixgroup", connection)
        group_reader = ldap3.Reader(connection, obj_def, self.group_dn)
        username = username.lower()
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
    def __init__(self, host, domain, user_dn, group_dn,
        port=636, use_ssl=True, ca_cert=None, obsolete=False):
        tls_config = ldap3.Tls(validate=ssl.CERT_REQUIRED)
        if ca_cert is not None:
            tls_config = ldap3.Tls(validate=ssl.CERT_REQUIRED,
                ca_certs_file=ca_cert)
        self.server = ldap3.Server(host, port=port, use_ssl=use_ssl,
            tls=tls_config)
        self.domain = domain
        self.user_dn = user_dn
        self.group_dn = group_dn
        self.obsolete = obsolete

    def prepare_connection(self, username=None, password=None):
        if username is not None and password is not None:
            ad_user = "{}\\{}".format(self.domain, username)
            return ldap3.Connection(self.server, ad_user, password)
        return ldap3.Connection(self.server)
        
    def authenticate(self, username, password):
        try:
            return self.prepare_connection(username, password).bind()
        except ldap3.core.exceptions.LDAPSocketOpenError:
            return False

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
                    key, group, next_char = group_dn_parts[0]
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
        user = User.from_hashstring(string)
        if user is None:
            return False
        session_duration = datetime.now() - user.timestamp
        macs_equal = hmac.compare_digest(maccer.hexdigest().encode("utf-8"), hash)
        time_short = int(session_duration.total_seconds()) < self.max_duration 
        return macs_equal and time_short

