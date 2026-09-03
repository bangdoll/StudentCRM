"""routers/__init__.py
領域路由套件 (Domain Routers Package)。
"""

from .coach import router as coach_router
from .student import router as student_router
from .apple_ceo import router as apple_ceo_router
from .hub import router as hub_router

__all__ = [
    "coach_router",
    "student_router",
    "apple_ceo_router",
    "hub_router",
]
