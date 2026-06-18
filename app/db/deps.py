# app/db/deps.py
from fastapi import Depends

from app.core.config import settings
from app.db.repos.schedule import ScheduleRepository
from app.db.repos.user import UserRepository
from app.db.repos.admin import AdminRepository
from app.db.repos.worker import WorkerRepository
from app.db.repos.export import ExportRepository
from app.db.repos.monthly_progress import MonthlyProgressRepository


def get_db_path() -> str:
    return settings.sqlite_db_path


def get_schedule_repo(db_path: str = Depends(get_db_path)) -> ScheduleRepository:
    return ScheduleRepository(db_path)


def get_user_repo(db_path: str = Depends(get_db_path)) -> UserRepository:
    return UserRepository(db_path)


def get_admin_repo(db_path: str = Depends(get_db_path)) -> AdminRepository:
    return AdminRepository(db_path)


def get_worker_repo(db_path: str = Depends(get_db_path)) -> WorkerRepository:
    return WorkerRepository(db_path)


def get_export_repo(db_path: str = Depends(get_db_path)) -> ExportRepository:
    return ExportRepository(db_path)


def get_monthly_progress_repo(db_path: str = Depends(get_db_path)) -> MonthlyProgressRepository:
    return MonthlyProgressRepository(db_path)
