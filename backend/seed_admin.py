"""Creates (or resets the password of) the first admin account.

Usage: python seed_admin.py <username> <password>
"""

import sys

from app.database import Base, SessionLocal, engine
from app.migrations import run_migrations
from app.models import User
from app.security import hash_password


def main():
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(1)
    username, password = sys.argv[1], sys.argv[2]

    Base.metadata.create_all(bind=engine)
    run_migrations(engine)
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.username == username).first()
        if user:
            user.password_hash = hash_password(password)
            user.role = "admin"
            user.is_active = True
            print(f"已重置用户 {username} 的密码，设为 admin，并确保账号处于启用状态")
        else:
            user = User(username=username, password_hash=hash_password(password), role="admin")
            db.add(user)
            print(f"已创建管理员账号 {username}")
        db.commit()
    finally:
        db.close()


if __name__ == "__main__":
    main()
