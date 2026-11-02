from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session


from backend.db.engin import get_db
from backend.auth import get_current_admin
from backend.schema._input import ClientInput, ClientUpdateInput
from backend.services import (
    add_new_user,
    update_a_user,
    delete_a_user,
    get_all_users_from_panel,
    reset_a_user_usage,
)

router = APIRouter(prefix="/admin", tags=["Admin"])


@router.get("/user", description="Get all users")
async def get_all_users(
    db: Session = Depends(get_db), current_admin: dict = Depends(get_current_admin)
):
    if current_admin["role"] != "admin":
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={"detail": "Not authorized to access this resource."},
        )

    result = await get_all_users_from_panel(
        admin_username=current_admin["username"], db=db
    )
    return result


@router.post("/user", description="Add a new user")
async def add_user(
    user_input: ClientInput,
    db: Session = Depends(get_db),
    current_admin: dict = Depends(get_current_admin),
):
    if current_admin["role"] != "admin":
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={"detail": "Not authorized to access this resource."},
        )

    result = await add_new_user(
        admin_username=current_admin["username"], user_input=user_input, db=db
    )
    return result


@router.put("/user/{uuid}", description="Update an existing user")
async def update_user(
    uuid: str,
    user_input: ClientUpdateInput,
    db: Session = Depends(get_db),
    current_admin: dict = Depends(get_current_admin),
):
    if current_admin["role"] != "admin":
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={"detail": "Not authorized to access this resource."},
        )

    result = await update_a_user(
        admin_username=current_admin["username"],
        uuid=uuid,
        user_input=user_input,
        db=db,
    )
    return result


@router.put("/user/{email}/reset", description="Reset user usage statistics")
async def reset_user_usage(
    email: str,
    db: Session = Depends(get_db),
    current_admin: dict = Depends(get_current_admin),
):
    if current_admin["role"] != "admin":
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={"detail": "Not authorized to access this resource."},
        )

    result = await reset_a_user_usage(
        admin_username=current_admin["username"], email=email, db=db
    )
    return result


@router.delete("/user/{uuid}", description="Delete a user")
async def delete_user(
    uuid: str,
    db: Session = Depends(get_db),
    current_admin: dict = Depends(get_current_admin),
):
    if current_admin["role"] != "admin":
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={"detail": "Not authorized to access this resource."},
        )

    result = await delete_a_user(
        admin_username=current_admin["username"], uuid=uuid, db=db
    )
    return result
