from __future__ import annotations

NO_ADMIN_STATUS = (
    "You don't have permission to use Cursor Usage. A Cursor admin role is required."
)

_ADMIN_ROLES = frozenset(
    {
        "admin",
        "owner",
        "unpaid-admin",
        "unpaid admin",
        "free-owner",
        "free owner",
        "administrator",
        "team-admin",
        "team admin",
    }
)
_ROLE_KEYS = (
    "role",
    "teamRole",
    "membershipRole",
    "roleName",
    "userRole",
    "cursorRole",
)


def _normalize_role(value: object) -> str:
    text = " ".join(str(value or "").strip().casefold().replace("_", "-").split())
    return text.replace(" ", "-") if text else ""


def is_admin_role(value: object) -> bool:
    if value is True:
        return True
    if value is False or value is None:
        return False
    role = _normalize_role(value)
    if not role:
        return False
    if role in _ADMIN_ROLES or role.replace("-", " ") in _ADMIN_ROLES:
        return True
    return role.endswith("-admin") or role.endswith("-owner")


def extract_role(payload: object) -> str | None:
    if not isinstance(payload, dict):
        return None
    for key in _ROLE_KEYS:
        raw = payload.get(key)
        if raw not in (None, ""):
            return str(raw)
    if payload.get("isAdmin") is True or payload.get("isOwner") is True:
        return "admin"
    for nested_key in ("membership", "teamMembership", "team", "user"):
        nested = extract_role(payload.get(nested_key))
        if nested:
            return nested
    return None


def member_role_for_email(payload: object, email: str | None) -> str | None:
    if not email or not isinstance(payload, dict):
        return extract_role(payload)
    want = email.casefold()
    raw = (
        payload.get("teamMembers")
        or payload.get("members")
        or payload.get("users")
        or []
    )
    if not isinstance(raw, list):
        return extract_role(payload)
    for item in raw:
        if not isinstance(item, dict):
            continue
        member_email = item.get("email") or item.get("userEmail")
        if not member_email or str(member_email).casefold() != want:
            continue
        return extract_role(item) or extract_role(payload)
    return None


def snapshot_lacks_admin(snapshot) -> bool:
    return getattr(snapshot, "status", None) == NO_ADMIN_STATUS
