from datetime import datetime
from sqlalchemy.orm import Session

from backend.db import crud


class AdminLimiter:
    def __init__(self, db: Session, admin_username: str):
        self.db = db
        self.admin_username = admin_username
        self.admin = crud.get_admin_by_username(db, username=admin_username)

    def admin_is_active(self) -> bool:
        if self.admin.expiry_date is None:
            return self.admin.is_active

        is_expired = self.admin.expiry_date < datetime.utcnow()

        if is_expired and self.admin.is_active:
            crud.change_admin_status(self.db, self.admin.id)
            return False

        return self.admin.is_active

    def check_traffic_limit(self, required_traffic: int) -> bool:
        """Check if the admin has enough traffic to perform an operation."""
        if self.admin.traffic < required_traffic:
            return False
        return True

    def reduce_usage(self, total_traffic: int, usage_traffic: int) -> None:
        if self.admin.update_return_traffic:
            crud.reduce_admin_traffic(self.db, self.admin, usage_traffic)
            return
        crud.reduce_admin_traffic(self.db, self.admin, total_traffic)

    def increase_usage(self, traffic: int) -> None:
        if self.admin.delete_return_traffic:
            crud.increase_admin_traffic(self.db, self.admin, traffic)

    def apply_update(self, old_total: int, new_total: int, used: int = 0) -> None:
        """Adjust the admin's remaining traffic by the change in a user's committed
        traffic, where committed = max(limit, used). Already-consumed traffic is
        never refunded, so lowering the limit of a used-up user refunds nothing,
        and raising it only charges the part above what's already committed.
        (e.g. a fully-used 80 GB user: 80->20 refunds 0, then 20->100 charges 20.)"""
        delta = max(new_total, used) - max(old_total, used)
        if delta > 0:
            crud.reduce_admin_traffic(self.db, self.admin, delta)
        elif delta < 0 and self.admin.update_return_traffic:
            crud.increase_admin_traffic(self.db, self.admin, -delta)

    def charge(self, amount: int) -> None:
        """Unconditionally deduct traffic from the admin's budget. Used on reset:
        resetting a user's usage frees the already-consumed traffic for re-use,
        so that amount is charged back regardless of the return-traffic flags."""
        if amount > 0:
            crud.reduce_admin_traffic(self.db, self.admin, amount)
