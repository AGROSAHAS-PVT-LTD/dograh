import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from loguru import logger

from api.constants import UI_APP_URL
from api.db import db_client
from api.db.models import OrganizationInvitationModel, UserModel
from api.enums import InvitationStatus, OrganizationRole
from api.schemas.team import (
    AcceptInvitationRequest,
    InvitationResponse,
    InviteMemberRequest,
    MessageResponse,
    TeamMemberResponse,
    TeamResponse,
    UpdateMemberRoleRequest,
)
from api.services.auth.depends import get_user
from api.services.email import send_invitation_email
from api.services.saas.access import (
    OrganizationAccess,
    get_organization_access,
    require_organization_roles,
)
from api.services.saas.entitlements import assert_seat_capacity, get_entitlements

router = APIRouter(prefix="/team", tags=["team"])

INVITATION_TTL_DAYS = 7


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _invite_url(token: str) -> str:
    return f"{UI_APP_URL.rstrip('/')}/invite?token={token}"


def _invitation_response(
    invitation: OrganizationInvitationModel,
    invite_url: str | None = None,
    *,
    email_sent: bool = False,
) -> InvitationResponse:
    return InvitationResponse(
        id=invitation.id,
        email=invitation.email,
        role=OrganizationRole(invitation.role),
        status=invitation.status,
        expires_at=invitation.expires_at,
        created_at=invitation.created_at,
        invite_url=invite_url,
        email_sent=email_sent,
    )


async def _team_response(organization_id: int) -> TeamResponse:
    members = await db_client.get_organization_members_with_roles(organization_id)
    invitations = await db_client.list_pending_invitations(organization_id)
    entitlements = await get_entitlements(organization_id)
    return TeamResponse(
        organization_id=organization_id,
        members=[
            TeamMemberResponse(
                user_id=member.id,
                email=member.email,
                name=None,
                role=OrganizationRole(role),
            )
            for member, role in members
        ],
        invitations=[_invitation_response(invitation) for invitation in invitations],
        seats_used=len(members),
        seats_limit=entitlements["plan"]["limits"]["seats"],
    )


@router.get("/members", response_model=TeamResponse)
async def list_team(
    access: OrganizationAccess = Depends(get_organization_access),
) -> TeamResponse:
    return await _team_response(access.organization_id)


@router.post("/invitations", response_model=InvitationResponse, status_code=201)
async def invite_member(
    request: InviteMemberRequest,
    access: OrganizationAccess = Depends(
        require_organization_roles(OrganizationRole.OWNER, OrganizationRole.ADMIN)
    ),
) -> InvitationResponse:
    await assert_seat_capacity(access.organization_id)

    existing_user = await db_client.get_user_by_email(request.email)
    if existing_user:
        role = await db_client.get_user_role(existing_user.id, access.organization_id)
        if role:
            raise HTTPException(
                status_code=409,
                detail="That person is already a member of this organization",
            )

    pending = await db_client.get_pending_invitation_by_email(
        access.organization_id, request.email
    )
    if pending:
        await db_client.revoke_invitation(pending.id, access.organization_id)

    token = secrets.token_urlsafe(32)
    invitation = await db_client.create_invitation(
        organization_id=access.organization_id,
        email=str(request.email),
        role=request.role,
        token_hash=_token_hash(token),
        invited_by=access.user.id,
        expires_at=datetime.now(UTC) + timedelta(days=INVITATION_TTL_DAYS),
    )
    invite_url = _invite_url(token)
    email_sent = False
    try:
        email_sent = await send_invitation_email(
            to_email=str(request.email),
            invite_url=invite_url,
            role=request.role.value,
            inviter_email=access.user.email,
            expires_at=invitation.expires_at.strftime("%Y-%m-%d %H:%M UTC"),
        )
    except Exception as exc:
        logger.warning("Could not send invitation email to {}: {}", request.email, exc)
    return _invitation_response(invitation, invite_url, email_sent=email_sent)


@router.delete("/invitations/{invitation_id}", response_model=MessageResponse)
async def revoke_invitation(
    invitation_id: int,
    access: OrganizationAccess = Depends(
        require_organization_roles(OrganizationRole.OWNER, OrganizationRole.ADMIN)
    ),
) -> MessageResponse:
    revoked = await db_client.revoke_invitation(invitation_id, access.organization_id)
    if not revoked:
        raise HTTPException(status_code=404, detail="Pending invitation not found")
    return MessageResponse(message="Invitation revoked")


@router.post("/invitations/accept", response_model=MessageResponse)
async def accept_invitation(
    request: AcceptInvitationRequest,
    user: UserModel = Depends(get_user),
) -> MessageResponse:
    invitation = await db_client.get_invitation_by_token_hash(
        _token_hash(request.token)
    )
    if invitation is None:
        raise HTTPException(status_code=404, detail="Invitation not found")
    if invitation.status != InvitationStatus.PENDING.value:
        raise HTTPException(status_code=409, detail="Invitation is no longer pending")
    if invitation.expires_at <= datetime.now(UTC):
        raise HTTPException(status_code=410, detail="Invitation has expired")
    if not user.email or user.email.strip().lower() != invitation.email.lower():
        raise HTTPException(
            status_code=403, detail="Sign in with the email address that was invited"
        )

    if not await db_client.is_user_member_of_organization(
        user.id, invitation.organization_id
    ):
        await db_client.add_user_to_organization(
            user.id,
            invitation.organization_id,
            role=OrganizationRole(invitation.role),
        )
    await db_client.accept_invitation(invitation.id)
    await db_client.update_user_selected_organization(
        user.id, invitation.organization_id
    )
    return MessageResponse(message="Invitation accepted")


@router.patch("/members/{user_id}", response_model=MessageResponse)
async def update_member_role(
    user_id: int,
    request: UpdateMemberRoleRequest,
    access: OrganizationAccess = Depends(
        require_organization_roles(OrganizationRole.OWNER, OrganizationRole.ADMIN)
    ),
) -> MessageResponse:
    if user_id == access.user.id:
        raise HTTPException(status_code=400, detail="You cannot change your own role")

    current_role = await db_client.get_user_role(user_id, access.organization_id)
    if current_role is None:
        raise HTTPException(status_code=404, detail="Member not found")
    if current_role == OrganizationRole.OWNER.value:
        raise HTTPException(status_code=400, detail="Ownership cannot be changed here")
    if access.role == OrganizationRole.ADMIN and (
        current_role == OrganizationRole.ADMIN.value
        or request.role == OrganizationRole.ADMIN
    ):
        raise HTTPException(
            status_code=403, detail="Only an owner can manage admin roles"
        )

    await db_client.set_user_role(user_id, access.organization_id, request.role)
    return MessageResponse(message="Member role updated")


@router.delete("/members/{user_id}", response_model=MessageResponse)
async def remove_member(
    user_id: int,
    access: OrganizationAccess = Depends(
        require_organization_roles(OrganizationRole.OWNER, OrganizationRole.ADMIN)
    ),
) -> MessageResponse:
    if user_id == access.user.id:
        raise HTTPException(status_code=400, detail="You cannot remove yourself")

    current_role = await db_client.get_user_role(user_id, access.organization_id)
    if current_role is None:
        raise HTTPException(status_code=404, detail="Member not found")
    if current_role == OrganizationRole.OWNER.value:
        raise HTTPException(status_code=400, detail="The owner cannot be removed")
    if (
        access.role == OrganizationRole.ADMIN
        and current_role == OrganizationRole.ADMIN.value
    ):
        raise HTTPException(status_code=403, detail="Only an owner can remove an admin")

    await db_client.remove_user_from_organization(user_id, access.organization_id)
    return MessageResponse(message="Member removed")
