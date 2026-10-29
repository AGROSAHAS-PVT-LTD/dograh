import { client } from '@/client/client.gen';

export type OrganizationRole = 'owner' | 'admin' | 'member';

export interface TeamMember {
    user_id: number;
    email: string | null;
    name: string | null;
    role: OrganizationRole;
}

export interface Invitation {
    id: number;
    email: string;
    role: OrganizationRole;
    status: string;
    expires_at: string;
    created_at: string | null;
    invite_url?: string | null;
    email_sent?: boolean;
}

export interface TeamResponse {
    organization_id: number;
    members: TeamMember[];
    invitations: Invitation[];
    seats_used: number;
    seats_limit: number;
}

export interface Plan {
    code: string;
    name: string;
    description: string;
    base_price_usd_cents: number;
    price_usd: number;
    price_cents: number;
    price_display: string;
    currency: string;
    billing_interval: string;
    fx_rate: number | null;
    fx_buffer_percent: number | null;
    billing_configured: boolean;
    limits: Record<string, number>;
    features: string[];
}

export interface Entitlements {
    organization_id: number;
    plan: Plan;
    subscription_status: string;
    is_active: boolean;
    provider: string | null;
    billing_interval: string;
    currency: string;
    amount_minor: number | null;
    cancel_at_period_end: boolean;
    current_period_end: string | null;
    usage: Record<string, number>;
    remaining: Record<string, number>;
}

export interface CheckoutResponse {
    checkout_url: string;
    tx_ref: string;
    amount_minor: number;
    currency: string;
    price_display: string;
}

export interface CurrencyOption {
    code: string;
    country: string;
}

function baseUrl(): string {
    return client.getConfig().baseUrl || window.location.origin;
}

async function request<T>(
    path: string,
    token: string | null,
    init: RequestInit = {}
): Promise<T> {
    const headers = new Headers(init.headers);
    headers.set('Content-Type', 'application/json');
    if (token) headers.set('Authorization', `Bearer ${token}`);
    const response = await fetch(`${baseUrl()}/api/v1${path}`, {
        ...init,
        headers,
    });
    const text = await response.text();
    let payload: unknown = null;
    try {
        payload = text ? JSON.parse(text) : null;
    } catch {
        payload = text;
    }
    if (!response.ok) {
        const detail =
            payload && typeof payload === 'object' && 'detail' in payload
                ? String((payload as { detail: unknown }).detail)
                : `Request failed (${response.status})`;
        throw new Error(detail);
    }
    return payload as T;
}

export function getTeam(token: string) {
    return request<TeamResponse>('/team/members', token);
}

export function inviteMember(
    token: string,
    email: string,
    role: OrganizationRole
) {
    return request<Invitation>('/team/invitations', token, {
        method: 'POST',
        body: JSON.stringify({ email, role }),
    });
}

export function revokeInvitation(token: string, invitationId: number) {
    return request<{ message: string }>(
        `/team/invitations/${invitationId}`,
        token,
        { method: 'DELETE' }
    );
}

export function updateMemberRole(
    token: string,
    userId: number,
    role: OrganizationRole
) {
    return request<{ message: string }>(`/team/members/${userId}`, token, {
        method: 'PATCH',
        body: JSON.stringify({ role }),
    });
}

export function removeMember(token: string, userId: number) {
    return request<{ message: string }>(`/team/members/${userId}`, token, {
        method: 'DELETE',
    });
}

export function acceptInvitation(token: string, inviteToken: string) {
    return request<{ message: string }>('/team/invitations/accept', token, {
        method: 'POST',
        body: JSON.stringify({ token: inviteToken }),
    });
}

export function getPlans(currency = 'USD', billingInterval = 'monthly') {
    const params = new URLSearchParams({
        currency,
        billing_interval: billingInterval,
    });
    return request<{
        plans: Plan[];
        currency: string;
        billing_interval: string;
        supported_currencies: CurrencyOption[];
    }>(`/saas/plans?${params.toString()}`, null);
}

export function getSubscription(token: string) {
    return request<{ entitlements: Entitlements }>('/saas/subscription', token);
}

export function createCheckout(
    token: string,
    planCode: string,
    currency: string,
    billingInterval: string
) {
    return request<CheckoutResponse>('/saas/checkout', token, {
        method: 'POST',
        body: JSON.stringify({
            plan_code: planCode,
            currency,
            billing_interval: billingInterval,
            success_url: `${window.location.origin}/plan?checkout=success`,
            cancel_url: `${window.location.origin}/plan?checkout=cancelled`,
        }),
    });
}

export function verifyCheckout(token: string, txRef: string) {
    return request<{ message: string; entitlements: Entitlements }>(
        '/saas/checkout/verify',
        token,
        {
            method: 'POST',
            body: JSON.stringify({ tx_ref: txRef }),
        }
    );
}

export function cancelSubscription(token: string) {
    return request<{ message: string; cancel_at_period_end: boolean }>(
        '/saas/cancel',
        token,
        { method: 'POST' }
    );
}

