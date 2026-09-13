from .start import router as start_router
from .topup import router as topup_router
from .change_password import router as change_password_router
from .wallet import router as wallet_router
from .admin_settings import router as admin_settings_router
from .user_search import router as user_search_router
from .partnership import router as partnership_router
from .tutorials import router as tutorials_router
from .approval import router as approval_router

all_routers = [
    start_router,
    topup_router,
    change_password_router,
    wallet_router,
    admin_settings_router,
    user_search_router,
    partnership_router,
    tutorials_router,
    approval_router,
]
