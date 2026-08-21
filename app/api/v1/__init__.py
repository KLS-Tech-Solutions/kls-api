from fastapi import APIRouter

from app.api.v1 import admin, admins, auth, enrollment, learning, public, student

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(public.router)
api_router.include_router(student.router)
api_router.include_router(enrollment.router)
api_router.include_router(admin.router)
api_router.include_router(admins.router)
api_router.include_router(learning.router)
