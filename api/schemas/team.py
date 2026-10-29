from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, field_validator

from api.enums import OrganizationRole


class TeamMemberResponse(BaseModel):
    user_id: int
    email: str | None
    name: str | None = None
    role: OrganizationRole


class InvitationResponse(BaseModel):
    id: int
    email: EmailStr
    role: OrganizationRole
    status: str
    expires_at: datetime
    created_at: datetime | None = None
    invite_url: str | None = None


class TeamResponse(BaseModel):
    organization_id: int
    members: list[TeamMemberResponse]
    invitations: list[InvitationResponse]
    seats_used: int
    seats_limit: int


class InviteMemberRequest(BaseModel):
    email: EmailStr
    role: OrganizationRole = OrganizationRole.MEMBER

    @field_validator("role")
    @classmethod
    def disallow_owner_invites(cls, value: OrganizationRole) -> OrganizationRole:
        if value == OrganizationRole.OWNER:
            raise ValueError("Ownership must be transferred, not invited")
        return value


class UpdateMemberRoleRequest(BaseModel):
    role: OrganizationRole

    @field_validator("role")
    @classmethod
    def disallow_owner_promotion(cls, value: OrganizationRole) -> OrganizationRole:
        if value == OrganizationRole.OWNER:
            raise ValueError("Ownership must be transferred, not assigned")
        return value


class AcceptInvitationRequest(BaseModel):
    token: str = Field(min_length=20)


class MessageResponse(BaseModel):
    message: str
