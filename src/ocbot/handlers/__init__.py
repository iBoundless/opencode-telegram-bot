from .menu import router as menu_router
from .models import router as models_router
from .new_task import router as new_task_router
from .permissions import router as permissions_router
from .prompts import router as prompts_router
from .service import router as service_router
from .sessions import router as sessions_router

__all__ = [
    "menu_router",
    "models_router",
    "new_task_router",
    "permissions_router",
    "prompts_router",
    "service_router",
    "sessions_router",
]
