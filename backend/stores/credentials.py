"""Validate untrusted login input before database lookups and password hashing."""

import json


def validate_username(username):
    if not isinstance(username, str) or not username.strip() or len(username) > 150 or "\x00" in username:
        raise ValueError("Invalid username")
    # JSON permits escaped lone surrogates that PostgreSQL and UTF-8 reject.
    username.encode("utf-8")
    return username.strip()


def parse_login_credentials(body):
    try:
        if len(body) > 16384:
            raise ValueError
        data = json.loads(body)
        if not isinstance(data, dict):
            raise ValueError
        username = validate_username(data.get("username"))
        password = data.get("password")
        if not isinstance(password, str) or not password or len(password) > 4096:
            raise ValueError
        password.encode("utf-8")
        return username, password
    except (ValueError, RecursionError) as error:
        raise ValueError("Enter your username and password.") from error
