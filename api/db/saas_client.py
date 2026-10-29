"""Database operations for SaaS roles, invitations, and subscriptions."""

from datetime import UTC, datetime
from typing import Optional

from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.postgresql import insert

from api.db.base_client import BaseDBClient
from api.db.models import (
    BillingEventModel,
    OrganizationInvitationModel,
    OrganizationSubscriptionModel,
    UserModel,
    WorkflowModel,
    organization_users_association,
)
from api.enums import InvitationStatus, OrganizationRole, WorkflowStatus


class SaaSClient(BaseDBClient):
    async def get_user_role(self, user_id: int, organization_id: int) -> str | None:
        async with self.async_session() as session:
            result = await session.execute(
                select(organization_users_association.c.role).where(
                    organization_users_association.c.user_id == user_id,
                    organization_users_association.c.organization_id == organization_id,
                )
            )
            return result.scalar_one_or_none()

    async def set_user_role(
        self, user_id: int, organization_id: int, role: OrganizationRole
    ) -> bool:
        async with self.async_session() as session:
            result = await session.execute(
                update(organization_users_association)
                .where(
                    organization_users_association.c.user_id == user_id,
                    organization_users_association.c.organization_id == organization_id,
                )
                .values(role=role.value)
            )
            await session.commit()
            return bool(result.rowcount)

    async def remove_user_from_organization(
        self, user_id: int, organization_id: int
    ) -> bool:
        async with self.async_session() as session:
            result = await session.execute(
                delete(organization_users_association).where(
                    organization_users_association.c.user_id == user_id,
                    organization_users_association.c.organization_id == organization_id,
                )
            )
            await session.commit()
            return bool(result.rowcount)

    async def get_organization_members_with_roles(
        self, organization_id: int
    ) -> list[tuple[UserModel, str]]:
        async with self.async_session() as session:
            result = await session.execute(
                select(UserModel, organization_users_association.c.role)
                .join(
                    organization_users_association,
                    organization_users_association.c.user_id == UserModel.id,
                )
                .where(
                    organization_users_association.c.organization_id == organization_id
                )
                .order_by(UserModel.id)
            )
            return [(row[0], row[1]) for row in result.all()]

    async def count_organization_owners(self, organization_id: int) -> int:
        async with self.async_session() as session:
            result = await session.execute(
                select(func.count())
                .select_from(organization_users_association)
                .where(
                    organization_users_association.c.organization_id == organization_id,
                    organization_users_association.c.role == OrganizationRole.OWNER.value,
                )
            )
            return int(result.scalar_one())

    async def count_active_workflows(self, organization_id: int) -> int:
        async with self.async_session() as session:
            result = await session.execute(
                select(func.count())
                .select_from(WorkflowModel)
                .where(
                    WorkflowModel.organization_id == organization_id,
                    WorkflowModel.status == WorkflowStatus.ACTIVE.value,
                )
            )
            return int(result.scalar_one())

    async def create_invitation(
        self,
        *,
        organization_id: int,
        email: str,
        role: OrganizationRole,
        token_hash: str,
        invited_by: int | None,
        expires_at: datetime,
    ) -> OrganizationInvitationModel:
        async with self.async_session() as session:
            invitation = OrganizationInvitationModel(
                organization_id=organization_id,
                email=email.strip().lower(),
                role=role.value,
                token_hash=token_hash,
                invited_by=invited_by,
                expires_at=expires_at,
                status=InvitationStatus.PENDING.value,
            )
            session.add(invitation)
            await session.commit()
            await session.refresh(invitation)
            return invitation

    async def list_pending_invitations(
        self, organization_id: int
    ) -> list[OrganizationInvitationModel]:
        async with self.async_session() as session:
            result = await session.execute(
                select(OrganizationInvitationModel)
                .where(
                    OrganizationInvitationModel.organization_id == organization_id,
                    OrganizationInvitationModel.status == InvitationStatus.PENDING.value,
                    OrganizationInvitationModel.expires_at > datetime.now(UTC),
                )
                .order_by(OrganizationInvitationModel.created_at.desc())
            )
            return list(result.scalars().all())

    async def get_invitation_by_token_hash(
        self, token_hash: str
    ) -> Optional[OrganizationInvitationModel]:
        async with self.async_session() as session:
            result = await session.execute(
                select(OrganizationInvitationModel).where(
                    OrganizationInvitationModel.token_hash == token_hash
                )
            )
            return result.scalars().first()

    async def get_pending_invitation_by_email(
        self, organization_id: int, email: str
    ) -> Optional[OrganizationInvitationModel]:
        async with self.async_session() as session:
            result = await session.execute(
                select(OrganizationInvitationModel)
                .where(
                    OrganizationInvitationModel.organization_id == organization_id,
                    OrganizationInvitationModel.email == email.strip().lower(),
                    OrganizationInvitationModel.status == InvitationStatus.PENDING.value,
                    OrganizationInvitationModel.expires_at > datetime.now(UTC),
                )
                .order_by(OrganizationInvitationModel.created_at.desc())
            )
            return result.scalars().first()

    async def accept_invitation(self, invitation_id: int) -> None:
        async with self.async_session() as session:
            await session.execute(
                update(OrganizationInvitationModel)
                .where(OrganizationInvitationModel.id == invitation_id)
                .values(
                    status=InvitationStatus.ACCEPTED.value,
                    accepted_at=datetime.now(UTC),
                )
            )
            await session.commit()

    async def revoke_invitation(
        self, invitation_id: int, organization_id: int
    ) -> bool:
        async with self.async_session() as session:
            result = await session.execute(
                update(OrganizationInvitationModel)
                .where(
                    OrganizationInvitationModel.id == invitation_id,
                    OrganizationInvitationModel.organization_id == organization_id,
                    OrganizationInvitationModel.status == InvitationStatus.PENDING.value,
                )
                .values(status=InvitationStatus.REVOKED.value)
            )
            await session.commit()
            return bool(result.rowcount)

    async def get_subscription(
        self, organization_id: int
    ) -> Optional[OrganizationSubscriptionModel]:
        async with self.async_session() as session:
            result = await session.execute(
                select(OrganizationSubscriptionModel).where(
                    OrganizationSubscriptionModel.organization_id == organization_id
                )
            )
            return result.scalars().first()

    async def get_subscription_by_tx_ref(
        self, tx_ref: str
    ) -> Optional[OrganizationSubscriptionModel]:
        async with self.async_session() as session:
            result = await session.execute(
                select(OrganizationSubscriptionModel).where(
                    OrganizationSubscriptionModel.checkout_tx_ref == tx_ref
                )
            )
            return result.scalars().first()

    async def get_subscription_by_provider_plan(
        self, provider_plan_id: str
    ) -> Optional[OrganizationSubscriptionModel]:
        async with self.async_session() as session:
            result = await session.execute(
                select(OrganizationSubscriptionModel).where(
                    OrganizationSubscriptionModel.provider_plan_id
                    == provider_plan_id
                )
            )
            return result.scalars().first()

    async def get_subscription_by_provider_subscription(
        self, provider_subscription_id: str
    ) -> Optional[OrganizationSubscriptionModel]:
        async with self.async_session() as session:
            result = await session.execute(
                select(OrganizationSubscriptionModel).where(
                    OrganizationSubscriptionModel.provider_subscription_id
                    == provider_subscription_id
                )
            )
            return result.scalars().first()

    async def upsert_subscription(
        self,
        *,
        organization_id: int,
        plan_code: str,
        status: str,
        provider: str = "flutterwave",
        provider_customer_id: str | None = None,
        provider_subscription_id: str | None = None,
        provider_plan_id: str | None = None,
        currency: str = "USD",
        billing_interval: str = "monthly",
        amount_minor: int | None = None,
        checkout_tx_ref: str | None = None,
        pending_plan_code: str | None = None,
        pending_currency: str | None = None,
        pending_billing_interval: str | None = None,
        pending_amount_minor: int | None = None,
        pending_provider_plan_id: str | None = None,
        clear_pending: bool = False,
        current_period_start: datetime | None = None,
        current_period_end: datetime | None = None,
        cancel_at_period_end: bool = False,
        trial_end: datetime | None = None,
    ) -> OrganizationSubscriptionModel:
        async with self.async_session() as session:
            result = await session.execute(
                select(OrganizationSubscriptionModel).where(
                    OrganizationSubscriptionModel.organization_id == organization_id
                )
            )
            subscription = result.scalars().first()
            if subscription is None:
                subscription = OrganizationSubscriptionModel(
                    organization_id=organization_id
                )
                session.add(subscription)
            subscription.plan_code = plan_code
            subscription.status = status
            subscription.provider = provider
            if provider_customer_id is not None:
                subscription.provider_customer_id = provider_customer_id
            if provider_subscription_id is not None:
                subscription.provider_subscription_id = provider_subscription_id
            if provider_plan_id is not None:
                subscription.provider_plan_id = provider_plan_id
            if currency:
                subscription.currency = currency
            if billing_interval:
                subscription.billing_interval = billing_interval
            if amount_minor is not None:
                subscription.amount_minor = amount_minor
            if checkout_tx_ref is not None:
                subscription.checkout_tx_ref = checkout_tx_ref
            if clear_pending:
                subscription.pending_plan_code = None
                subscription.pending_currency = None
                subscription.pending_billing_interval = None
                subscription.pending_amount_minor = None
                subscription.pending_provider_plan_id = None
            else:
                if pending_plan_code is not None:
                    subscription.pending_plan_code = pending_plan_code
                if pending_currency is not None:
                    subscription.pending_currency = pending_currency
                if pending_billing_interval is not None:
                    subscription.pending_billing_interval = pending_billing_interval
                if pending_amount_minor is not None:
                    subscription.pending_amount_minor = pending_amount_minor
                if pending_provider_plan_id is not None:
                    subscription.pending_provider_plan_id = pending_provider_plan_id
            if current_period_start is not None:
                subscription.current_period_start = current_period_start
            if current_period_end is not None:
                subscription.current_period_end = current_period_end
            subscription.cancel_at_period_end = cancel_at_period_end
            if trial_end is not None:
                subscription.trial_end = trial_end
            await session.commit()
            await session.refresh(subscription)
            return subscription

    async def billing_event_exists(self, event_key: str) -> bool:
        async with self.async_session() as session:
            result = await session.execute(
                select(BillingEventModel.id).where(
                    BillingEventModel.event_key == event_key
                )
            )
            return result.scalar_one_or_none() is not None

    async def record_billing_event(
        self,
        *,
        event_key: str,
        event_type: str,
        payload: dict,
        provider: str = "flutterwave",
    ) -> bool:
        """Insert an event idempotently; return True if it is new."""
        async with self.async_session() as session:
            stmt = (
                insert(BillingEventModel)
                .values(
                    provider=provider,
                    event_key=event_key,
                    event_type=event_type,
                    payload=payload,
                )
                .on_conflict_do_nothing(index_elements=["event_key"])
            )
            result = await session.execute(stmt)
            await session.commit()
            return bool(result.rowcount)

