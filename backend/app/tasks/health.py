"""Periodic CHR health probe (separate from polling so brief outages don't block detection)."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from sqlalchemy import select

from app.database import SessionLocal
from app.models.chr_node import CHRNode
from app.services.chr_api import CHRClient
from app.services.crypto import decrypt
from app.services.chr_api import CHRConnectionInfo
from app.services.pubsub import CH_CHR_STATUS, publish
from app.tasks._runner import run
from app.tasks.celery_app import celery_app


@celery_app.task(name="app.tasks.health.health_check_chrs")
def health_check_chrs() -> dict:
    return run(_check())


async def _ping(node: CHRNode) -> tuple[CHRNode, bool]:
    info = CHRConnectionInfo(
        host=node.host,
        port=node.api_port,
        username=node.username,
        password=decrypt(node.password_enc),
        use_ssl=bool(node.use_ssl),
    )
    try:
        async with CHRClient(info) as api:
            await api.identity()
        return node, True
    except Exception:
        return node, False


async def _check() -> dict:
    online = 0
    offline = 0
    async with SessionLocal() as session:
        nodes = (await session.execute(select(CHRNode))).scalars().all()
        if not nodes:
            return {"online": 0, "offline": 0}
        results = await asyncio.gather(*(_ping(n) for n in nodes))
        now = datetime.now(timezone.utc)
        for node, ok in results:
            prior = node.status
            node.status = "online" if ok else "offline"
            if ok:
                node.last_seen_at = now
                online += 1
            else:
                offline += 1
            if prior != node.status:
                await publish(
                    CH_CHR_STATUS,
                    {"chr_id": str(node.id), "name": node.name, "status": node.status},
                )
        await session.commit()
    return {"online": online, "offline": offline}
