import { NextResponse } from 'next/server';

import { getAuthProvider, getFirebaseConfig, getSignupEnabled, getStackConfig } from '@/lib/auth/config';
import logger from '@/lib/logger';

export async function GET() {
  const provider = await getAuthProvider();
  // When using Stack, hand the public client config to the browser so it can
  // initialize the Stack SDK at runtime (no build-time NEXT_PUBLIC_* needed).
  const stackConfig = provider === 'stack' ? await getStackConfig() : null;
  // Firebase public config is independent of the primary auth provider; the
  // local/OSS provider can still offer Google and phone sign-in.
  const firebaseConfig = await getFirebaseConfig();
  const signupEnabled = await getSignupEnabled();
  logger.debug(`Got provider ${provider} from getAuthProvider`)
  return NextResponse.json({
    provider,
    stackProjectId: stackConfig?.projectId ?? null,
    stackPublishableClientKey: stackConfig?.publishableClientKey ?? null,
    firebaseConfig,
    signupEnabled,
  });
}
