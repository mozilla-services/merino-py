"""v1 API router aggregation."""

from fastapi import APIRouter

from merino_fleece.api.v1 import pii, search_terms

router = APIRouter()
router.include_router(pii.router)
router.include_router(search_terms.router)
