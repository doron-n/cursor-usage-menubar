import unittest

from cursor_usage_menubar.roles import (
    NO_ADMIN_STATUS,
    extract_role,
    is_admin_role,
    member_role_for_email,
    snapshot_lacks_admin,
)
from cursor_usage_menubar.models import UsageSnapshot


class RolesTest(unittest.TestCase):
    def test_admin_roles(self):
        for role in ("admin", "owner", "unpaid-admin", "free-owner", "Administrator"):
            self.assertTrue(is_admin_role(role), role)
        self.assertTrue(is_admin_role(True))

    def test_member_roles_are_denied(self):
        for role in ("member", "user", None, False, ""):
            self.assertFalse(is_admin_role(role), role)

    def test_extract_role_from_nested_membership(self):
        self.assertEqual(extract_role({"membership": {"role": "owner"}}), "owner")
        self.assertEqual(extract_role({"isAdmin": True}), "admin")

    def test_member_role_matches_email(self):
        payload = {
            "teamMembers": [
                {"email": "ada@example.com", "role": "admin"},
                {"email": "bob@example.com", "role": "member"},
            ]
        }
        self.assertEqual(member_role_for_email(payload, "ada@example.com"), "admin")
        self.assertEqual(member_role_for_email(payload, "bob@example.com"), "member")
        self.assertIsNone(member_role_for_email(payload, "eve@example.com"))

    def test_snapshot_lacks_admin(self):
        self.assertTrue(snapshot_lacks_admin(UsageSnapshot.empty(NO_ADMIN_STATUS)))
        self.assertFalse(
            snapshot_lacks_admin(UsageSnapshot.empty("Open Cursor to refresh your session"))
        )
