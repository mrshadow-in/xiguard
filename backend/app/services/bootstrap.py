"""First-boot bootstrap: create initial admin user and empty mail configs."""
from __future__ import annotations

import logging

import bcrypt
from sqlalchemy import select

from app.config import settings
from app.database import SessionLocal
from app.models.mail_config import MAIL_HOSTING_NOC, MAIL_ISP_NOC, MailConfig
from app.models.user import User

logger = logging.getLogger(__name__)


async def bootstrap_admin_user() -> None:
    async with SessionLocal() as session:
        existing = await session.execute(select(User).limit(1))
        if existing.scalar_one_or_none() is None:
            password_hash = bcrypt.hashpw(
                settings.admin_password.encode("utf-8"), bcrypt.gensalt()
            ).decode("utf-8")
            session.add(User(username=settings.admin_username, password_hash=password_hash))
            logger.warning(
                "Created initial admin user '%s' — change password immediately.",
                settings.admin_username,
            )

        for ct in (MAIL_HOSTING_NOC, MAIL_ISP_NOC):
            res = await session.execute(select(MailConfig).where(MailConfig.config_type == ct))
            if res.scalar_one_or_none() is None:
                session.add(MailConfig(config_type=ct, enabled=False))

        await session.commit()
