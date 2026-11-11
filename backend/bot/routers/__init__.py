from .start import router as start_router
from .topup import router as topup_router
from .change_password import router as change_password_router
from .wallet import router as wallet_router
from .admin_settings import router as admin_settings_router
from .user_search import router as user_search_router
from .tutorials import router as tutorials_router
from .shop import router as shop_router
from .approval import router as approval_router
from .bot_provision import router as bot_provision_router

from .maintenance import router as maintenance_router

from .photo_fallback import router as photo_fallback_router

all_routers = [
    maintenance_router,
    start_router,
    topup_router,
    change_password_router,
    wallet_router,
    admin_settings_router,
    user_search_router,
    tutorials_router,
    shop_router,
    approval_router,
    bot_provision_router,
    # Last: only ever sees what no earlier handler wanted.
    photo_fallback_router,
]
