import hmac
import hashlib
import ssl
from datetime import datetime


class User:
    def __init__(self, username, groups, all_groups, timestamp=None,
                 obsolete=False, permanent=False):
        self.username = username
        self.groups = groups
        self.all_groups = all_groups
        if timestamp is not None:
            self.timestamp = timestamp
        else:
            self.timestamp = datetime.now()
        self.obsolete = obsolete
        self.permanent = permanent

    def summarize(self):
        return ":".join((
            self.username, ",".join(self.groups), ",".join(self.all_groups),
            str(self.timestamp.timestamp()), str(self.obsolete),
            str(self.permanent)))

    @staticmethod
    def from_summary(summary):
        parts = summary.split(":", 5)
        if len(parts) != 6:
            return None
        (name, group_str, all_group_str, timestamp_str, obsolete_str,
            permanent_str) = parts
        timestamp = datetime.fromtimestamp(float(timestamp_str))
        obsolete = obsolete_str == "True"
        groups = group_str.split(",")
        all_groups = group_str.split(",")
        permanent = permanent_str == "True"
        return User(name, groups, all_groups, timestamp, obsolete, permanent)

    @staticmethod
    def from_hashstring(secure_string):
        summary, hash = secure_string.split("=", 1)
        return User.from_summary(summary)


class UserManager:
    def __init__(self, backends):
        self.backends = backends

    def login(self, username, password, permanent=False):
        for backend in self.backends:
            if backend.authenticate(username, password):
                groups = sorted(list(set(backend.groups(username, password))))
                all_groups = sorted(list(set(backend.all_groups(
                    username, password))))
                return User(
                    username, groups, all_groups, obsolete=backend.obsolete,
                    permanent=permanent)
        return None


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
        macs_equal = hmac.compare_digest(
            maccer.hexdigest().encode("utf-8"), hash)
        time_short = int(session_duration.total_seconds()) < self.max_duration
        return macs_equal and (time_short or user.permanent)


class StaticUserManager:
    def __init__(self, users, obsolete=False):
        self.passwords = {
            username: password
            for (username, password, groups) in users
        }
        self.group_map = {
            username: groups
            for (username, password, groups) in users
        }
        self.obsolete = obsolete

    def authenticate(self, username, password):
        return (username in self.passwords
                and self.passwords[username] == password)

    def groups(self, username, password=None):
        if username in self.group_map:
            yield from self.group_map[username]

    def all_groups(self, username, password):
        yield from list(set(group for group in self.group_map.values()))


try:
    import ldap3

    class LdapManager:
        def __init__(self, host, user_dn, group_dn, port=636, use_ssl=True,
                     obsolete=False):
            self.server = ldap3.Server(host, port=port, use_ssl=use_ssl)
            self.user_dn = user_dn
            self.group_dn = group_dn
            self.obsolete = obsolete

        def authenticate(self, username, password):
            try:
                connection = ldap3.Connection(
                    self.server, self.user_dn.format(username), password)
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

        def all_groups(self, username, password):
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
                tls_config = ldap3.Tls(
                    validate=ssl.CERT_REQUIRED, ca_certs_file=ca_cert)
            self.server = ldap3.Server(
                host, port=port, use_ssl=use_ssl, tls=tls_config)
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
            if not connection.bind():
                return
            obj_def = ldap3.ObjectDef("user", connection)
            name_filter = "cn:={}".format(username)
            user_reader = ldap3.Reader(
                connection, obj_def, self.user_dn, name_filter)
            group_def = ldap3.ObjectDef("group", connection)

            all_group_reader = ldap3.Reader(
                connection, group_def, self.group_dn)
            all_groups = {
                group.primaryGroupToken.value: group
                for group in all_group_reader.search()
            }

            def _yield_recursive_groups(group_dn):
                group_reader = ldap3.Reader(
                    connection, group_def, group_dn)
                for entry in group_reader.search():
                    yield entry.name.value
                    for child in entry.memberOf:
                        yield from _yield_recursive_groups(child)
            for result in user_reader.search():
                yield from _yield_recursive_groups(
                    all_groups[result.primaryGroupID.value]
                    .distinguishedName.value)
                for group_dn in result.memberOf:
                    yield from _yield_recursive_groups(group_dn)

        def all_groups(self, username, password):
            connection = self.prepare_connection(username, password)
            if not connection.bind():
                return
            obj_def = ldap3.ObjectDef("group", connection)
            group_reader = ldap3.Reader(connection, obj_def, self.group_dn)
            for result in group_reader.search():
                yield result.name.value

except ImportError:
    pass


try:
    import grp
    import pwd
    import pam

    class PAMManager:
        def __init__(self, obsolete=False):
            self.pam = pam.pam()
            self.obsolete = obsolete

        def authenticate(self, username, password):
            return self.pam.authenticate(username, password)

        def groups(self, username, password=None):
            yield grp.getgrgid(pwd.getpwnam(username).pw_gid).gr_name
            for group in grp.getgrall():
                if username in group.gr_mem:
                    yield group.gr_name

        def all_groups(self, username, password):
            for group in grp.getgrall():
                yield group.gr_name
except ImportError:
    pass
