import hashlib
import ssl
from dataclasses import dataclass
from urllib.parse import urlsplit

from ldap3 import NONE, SUBTREE, Connection, Server, Tls
from ldap3.core.exceptions import LDAPException
from ldap3.utils.conv import escape_filter_chars

from app.core.config import Settings


class DirectoryUnavailable(Exception):
    pass


class DirectoryDenied(Exception):
    pass


@dataclass(frozen=True)
class DirectoryIdentity:
    directory_id: str
    username: str
    email: str
    role: str


def _connect(server: Server, dn: str, password: str, start_tls: bool, timeout: int):
    connection = Connection(
        server,
        user=dn,
        password=password,
        auto_referrals=False,
        receive_timeout=timeout,
        raise_exceptions=False,
    )
    try:
        connection.open()
        if connection.closed or (start_tls and not connection.start_tls()):
            raise DirectoryUnavailable()
        if not connection.bind():
            if connection.result.get("result") == 49:
                raise DirectoryDenied()
            raise DirectoryUnavailable()
        return connection
    except Exception:
        connection.unbind()
        raise


def authenticate(settings: Settings, login: str, password: str) -> DirectoryIdentity:
    if not settings.ldap_configured:
        raise DirectoryUnavailable()
    if not login.strip() or not password:
        raise DirectoryDenied()
    parsed = urlsplit(settings.ldap_url)
    if parsed.scheme not in {"ldap", "ldaps"} or not parsed.hostname or parsed.username:
        raise DirectoryUnavailable()
    service = None
    user = None
    try:
        tls = Tls(
            validate=ssl.CERT_REQUIRED,
            ca_certs_file=settings.ldap_ca_file,
            version=ssl.PROTOCOL_TLS_CLIENT,
        )
        server = Server(
            parsed.hostname,
            port=parsed.port or (636 if parsed.scheme == "ldaps" else 389),
            use_ssl=parsed.scheme == "ldaps",
            tls=tls,
            get_info=NONE,
            connect_timeout=settings.ldap_timeout_seconds,
        )
        try:
            service = _connect(
                server,
                settings.ldap_bind_dn,
                settings.ldap_bind_password.get_secret_value(),
                parsed.scheme == "ldap",
                settings.ldap_timeout_seconds,
            )
        except DirectoryDenied:
            raise DirectoryUnavailable() from None
        attributes = list(
            dict.fromkeys(
                [
                    settings.ldap_username_attribute,
                    settings.ldap_id_attribute,
                    "mail",
                    "memberOf",
                    "userAccountControl",
                ]
            )
        )
        query = settings.ldap_user_filter.replace("{login}", escape_filter_chars(login.strip()))
        if "{login}" not in settings.ldap_user_filter:
            raise DirectoryUnavailable()
        service.search(
            settings.ldap_base_dn,
            query,
            search_scope=SUBTREE,
            attributes=attributes,
            size_limit=2,
            time_limit=settings.ldap_timeout_seconds,
        )
        if service.result.get("result") != 0:
            raise DirectoryUnavailable()
        entries = [entry for entry in service.response if entry.get("type") == "searchResEntry"]
        if len(entries) != 1:
            raise DirectoryDenied()
        entry = entries[0]
        values = {key.lower(): value for key, value in entry["attributes"].items()}

        def first(name: str):
            value = values.get(name.lower())
            return value[0] if isinstance(value, list) and value else value

        if int(first("userAccountControl") or 0) & 2:
            raise DirectoryDenied()
        user = _connect(
            server, entry["dn"], password, parsed.scheme == "ldap", settings.ldap_timeout_seconds
        )
        groups = values.get("memberof") or []
        if isinstance(groups, str):
            groups = [groups]
        memberships = {str(group).casefold() for group in groups}
        roles = [
            role
            for group, role in settings.ldap_group_roles.items()
            if group.casefold() in memberships
        ]
        rank = {"none": 0, "viewer": 1, "dispatcher": 2, "admin": 3}
        role = max(roles, key=lambda value: rank[value]) if roles else settings.ldap_default_role
        if role == "none":
            raise DirectoryDenied()
        identifier = first(settings.ldap_id_attribute)
        username = str(first(settings.ldap_username_attribute) or "").strip().lower()
        email = str(first("mail") or "").strip().lower()
        if not identifier or not username or len(username) > 59 or not email or len(email) > 254:
            raise DirectoryDenied()
        digest = hashlib.sha256(
            (settings.ldap_url.lower() + ":" + str(identifier)).encode()
        ).hexdigest()
        return DirectoryIdentity(digest, "ldap:" + username, email, role)
    except (LDAPException, OSError, ValueError, TypeError):
        raise DirectoryUnavailable() from None
    finally:
        if user:
            user.unbind()
        if service:
            service.unbind()
