from fastapi import APIRouter

router = APIRouter(prefix="/test", tags=["test"])

@router.post("/execute")
def test_execute():
    pass

for route in router.routes:
    print(f"Path: {route.path}, Methods: {getattr(route, 'methods', None)}")
