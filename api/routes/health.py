from fastapi import APIRouter, JSONResponse

router = APIRouter()


@router.get("/health")
def health():
    return JSONResponse(content={"status": "ok"})


@router.get("/api/v1/health")
def health_v1():
    return JSONResponse(content={"status": "ok", "version": "0.1.0"})
