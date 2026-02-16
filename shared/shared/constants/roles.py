from enum import Enum


class Role(str, Enum):
    USER = "user"
    CREATOR = "creator"
    ADMIN = "admin"
    SUPER_ADMIN = "super_admin"
