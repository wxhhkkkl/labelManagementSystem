"""API v1 路由汇总。"""

from fastapi import APIRouter

from app.api.v1 import (
    allocations,
    audit as audit_api,
    auth,
    codes,
    dashboard,
    companies,
    imports,
    org,
    products,
    reports,
    templates,
    users,
    workstation_client,
    workstation_print,
    workstations,
)

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth.router)
api_router.include_router(companies.router)
api_router.include_router(workstations.router)
api_router.include_router(users.router)
api_router.include_router(org.router)
api_router.include_router(products.router)
api_router.include_router(imports.router)
api_router.include_router(codes.router)
api_router.include_router(allocations.router)
api_router.include_router(reports.router)
api_router.include_router(reports.ledger_router)
api_router.include_router(templates.router)
api_router.include_router(dashboard.router)
api_router.include_router(audit_api.router)
api_router.include_router(workstation_client.router)
api_router.include_router(workstation_print.router)
