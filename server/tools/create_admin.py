"""Create the first CMS super administrator after database migrations."""
from getpass import getpass

from app.api.admin import _hash_password
from app.db import SessionLocal
from app.models import AdminUser


def main():
    username = input("管理员用户名：").strip()
    password = getpass("密码：")
    if not 2 <= len(username) <= 50 or not 8 <= len(password) <= 128:
        raise SystemExit("用户名须为 2-50 字符，密码须为 8-128 字符")
    if password != getpass("确认密码："):
        raise SystemExit("两次密码不一致")
    with SessionLocal.begin() as db:
        if db.query(AdminUser.id).first():
            raise SystemExit("管理员账号已存在，请在 CMS 中管理账号")
        db.add(AdminUser(username=username, password_hash=_hash_password(password), role="super"))
    print("超级管理员已创建")


if __name__ == "__main__":
    main()
