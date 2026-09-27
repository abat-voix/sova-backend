import re


USER_GROUP_PREFIX = "user"
VALID_USER_ID = re.compile(r"^[A-Za-z0-9_-]+$")


def user_group_name(user_id: object) -> str:
    """Return the only group name a browser connection may join."""
    value = str(user_id)
    if not value or len(value) > 90 or VALID_USER_ID.fullmatch(value) is None:
        raise ValueError("Invalid realtime user id.")
    return f"{USER_GROUP_PREFIX}.{value}"
