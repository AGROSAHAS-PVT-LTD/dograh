"""Organization-scoped role checks for SaaS routes."""

from dataclasses import dataclass
from typing import Callable

from fastapi import Depends, HTTPException

from api.db import db_client
from api.db.models import UserModel
from api.enums import OrganizationRole
from api.services.auth.depends import get_user


@dataclass(frozen=True)
class OrganizationAccess:
    user: UserModel
    organization_id: int
    role: OrganizationRole


async def get_organization_access(
    user: UserModel = Depends(get_user),
) -> OrganizationAccess:
    organization_id = user.selected_organization_id
    if not organization_id:
        raise HTTPException(status_code=400, detail="No organization selected")

    role_value = await db_client.get_user_role(user.id, organization_id)
    if role_value is None:
        if not await db_client.is_user_member_of_organization(
            user.id, organization_id
        ):
            raise HTTPException(status_code=403, detail="Not a member of this organization")
        role_value = OrganizationRole.MEMBER.value

    try:
        role = OrganizationRole(role_value)
    except ValueError as exc:
        raise HTTPException(status_code=403, detail="Invalid organization role") from exc

    return OrganizationAccess(
        user=user,
        organization_id=organization_id,
        role=role,
    )


def require_organization_roles(
    *allowed: OrganizationRole,
) -> Callable:
    async def dependency(
        access: OrganizationAccess = Depends(get_organization_access),
    ) -> OrganizationAccess:
        if access.role not in allowed:
            raise HTTPException(
                status_code=403,
                detail="You do not have permission to perform this action",
            )
        return access

    return dependency
