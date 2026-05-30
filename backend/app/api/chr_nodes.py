"""CRUD + connection test for CHR nodes."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import func, select

from app.api.deps import CurrentUser, DB
from app.models.chr_node import CHRNode
from app.models.ip_pool import IPPool
from app.models.monitored_ip import MonitoredIP
from app.schemas.chr_node import CHRNodeCreate, CHRNodeOut, CHRNodeTestResult, CHRNodeUpdate
from app.services.chr_api import CHRConnectionInfo, test_connection
from app.services.crypto import encrypt, decrypt

router = APIRouter()


async def _augment(db, node: CHRNode) -> CHRNodeOut:
    pool_count = await db.scalar(
        select(func.count(IPPool.id)).where(IPPool.chr_node_id == node.id)
    )
    ip_count = await db.scalar(
        select(func.count(MonitoredIP.id))
        .join(IPPool, IPPool.id == MonitoredIP.pool_id)
        .where(IPPool.chr_node_id == node.id)
    )
    out = CHRNodeOut.model_validate(node)
    out.pool_count = pool_count or 0
    out.monitored_ip_count = ip_count or 0
    return out


@router.get("", response_model=list[CHRNodeOut])
async def list_nodes(_: CurrentUser, db: DB) -> list[CHRNodeOut]:
    rows = (await db.execute(select(CHRNode).order_by(CHRNode.name))).scalars().all()
    return [await _augment(db, n) for n in rows]


@router.post("", response_model=CHRNodeOut, status_code=status.HTTP_201_CREATED)
async def create_node(payload: CHRNodeCreate, _: CurrentUser, db: DB) -> CHRNodeOut:
    node = CHRNode(
        name=payload.name,
        host=payload.host,
        api_port=payload.api_port,
        username=payload.username,
        password_enc=encrypt(payload.password),
        use_ssl=payload.use_ssl,
        description=payload.description,
    )
    db.add(node)
    await db.commit()
    await db.refresh(node)
    return await _augment(db, node)


@router.get("/{node_id}", response_model=CHRNodeOut)
async def get_node(node_id: uuid.UUID, _: CurrentUser, db: DB) -> CHRNodeOut:
    node = await db.get(CHRNode, node_id)
    if not node:
        raise HTTPException(404, "CHR node not found")
    return await _augment(db, node)


@router.put("/{node_id}", response_model=CHRNodeOut)
async def update_node(
    node_id: uuid.UUID, payload: CHRNodeUpdate, _: CurrentUser, db: DB
) -> CHRNodeOut:
    node = await db.get(CHRNode, node_id)
    if not node:
        raise HTTPException(404, "CHR node not found")
    data = payload.model_dump(exclude_unset=True)
    if "password" in data and data["password"]:
        node.password_enc = encrypt(data.pop("password"))
    else:
        data.pop("password", None)
    for k, v in data.items():
        setattr(node, k, v)
    await db.commit()
    await db.refresh(node)
    return await _augment(db, node)


@router.delete("/{node_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_node(node_id: uuid.UUID, _: CurrentUser, db: DB) -> None:
    node = await db.get(CHRNode, node_id)
    if not node:
        raise HTTPException(404, "CHR node not found")
    await db.delete(node)
    await db.commit()


@router.post("/{node_id}/test", response_model=CHRNodeTestResult)
async def test_node(node_id: uuid.UUID, _: CurrentUser, db: DB) -> CHRNodeTestResult:
    node = await db.get(CHRNode, node_id)
    if not node:
        raise HTTPException(404, "CHR node not found")
    info = CHRConnectionInfo(
        host=node.host,
        port=node.api_port,
        username=node.username,
        password=decrypt(node.password_enc),
        use_ssl=bool(node.use_ssl),
    )
    res = await test_connection(info)
    return CHRNodeTestResult(**res)


@router.post("/{node_id}/test-blackhole")
async def test_blackhole(node_id: uuid.UUID, _: CurrentUser, db: DB) -> dict:
    """Diagnostic: push a blackhole on a TEST-NET-1 address, verify via
    /ip/route/print, then remove it. Returns step-by-step results so the
    operator can see exactly where the pipeline breaks."""
    from app.services.chr_api import CHRClient
    from datetime import datetime, timezone as _tz

    node = await db.get(CHRNode, node_id)
    if not node:
        raise HTTPException(404, "CHR node not found")

    test_ip = "192.0.2.123"  # RFC 5737 TEST-NET-1 — never routable
    comment = f"Xiguard test-blackhole {datetime.now(_tz.utc).isoformat()}"
    steps: list[dict] = []

    try:
        async with CHRClient.from_node(node) as api:
            # 1. Add (cycles through type=blackhole, blackhole=yes, gateway=blackhole)
            try:
                returned_id, syntax = await api.route_add_blackhole(test_ip, comment)
                steps.append({
                    "step": "add",
                    "ok": True,
                    "returned_id": returned_id,
                    "syntax_used": syntax,
                })
            except Exception as e:  # noqa: BLE001
                steps.append({"step": "add", "ok": False, "error": repr(e)})
                return {"ok": False, "test_ip": test_ip, "steps": steps}

            # 2. Verify
            try:
                found = await api.route_find_xiguard(test_ip)
                steps.append({
                    "step": "verify",
                    "ok": bool(found),
                    "found_count": len(found),
                    "first_id": found[0].get(".id") if found else None,
                })
            except Exception as e:  # noqa: BLE001
                steps.append({"step": "verify", "ok": False, "error": repr(e)})
                return {"ok": False, "test_ip": test_ip, "steps": steps}

            # 3. Cleanup — always try, even if verify failed
            try:
                removed = await api.route_remove_xiguard(test_ip)
                steps.append({"step": "remove", "ok": True, "removed": removed})
            except Exception as e:  # noqa: BLE001
                steps.append({"step": "remove", "ok": False, "error": repr(e)})
    except Exception as e:  # noqa: BLE001
        steps.append({"step": "connect", "ok": False, "error": repr(e)})
        return {"ok": False, "test_ip": test_ip, "steps": steps}

    overall = all(s.get("ok") for s in steps)
    return {"ok": overall, "test_ip": test_ip, "steps": steps}
