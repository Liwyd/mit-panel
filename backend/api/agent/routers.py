"""Endpoint the lightweight per-server agent talks to.

Deliberately outside the superadmin/admin auth scheme: the agent identifies
itself with the per-server token issued when the server was added (checked
against the DB on every call, not a shared secret), and it's the only party
that ever calls this. No listening port is needed on the monitored server -
the agent only ever makes outbound requests, which is what keeps it usable
behind NAT/firewalls without opening anything up.
"""

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from backend.db import crud
from backend.db.engin import get_db
from backend.db.model import Servers
from backend.schema._input import ServerHeartbeatInput

router = APIRouter(prefix="/agent", tags=["Agent"])


def _verify_agent_token(
    x_agent_token: str = Header(..., alias="X-Agent-Token"),
    db: Session = Depends(get_db),
) -> Servers:
    server = crud.get_server_by_token(db, x_agent_token)
    if not server:
        raise HTTPException(status_code=401, detail="Invalid agent token")
    return server


@router.post("/heartbeat", description="Agent metrics push")
async def heartbeat(
    metrics: ServerHeartbeatInput,
    db: Session = Depends(get_db),
    server: Servers = Depends(_verify_agent_token),
):
    reboot_pending = crud.record_server_heartbeat(db, server, metrics.model_dump())
    return {"reboot": reboot_pending}
