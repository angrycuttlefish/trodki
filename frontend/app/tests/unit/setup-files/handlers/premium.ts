import type { ActionResult } from '@rotki/common';
import process from 'node:process';
import { http, HttpResponse } from 'msw';
import { type PremiumCapabilities, PremiumFeature } from '@/modules/session/types';

const backendUrl = process.env.VITE_BACKEND_URL;

const mockPremiumCapabilitiesResponse: ActionResult<PremiumCapabilities> = {
  result: {
    [PremiumFeature.ASSET_MOVEMENT_MATCHING]: { enabled: true, minimumTier: 'Free' },
    [PremiumFeature.ETH_STAKING_VIEW]: { enabled: true, minimumTier: 'Free' },
    [PremiumFeature.EVENT_ANALYSIS_VIEW]: { enabled: true, minimumTier: 'Free' },
    [PremiumFeature.GRAPHS_VIEW]: { enabled: true, minimumTier: 'Free' },
  },
  message: '',
};

export const premiumHandlers = [
  // GET /api/1/premium/capabilities
  http.get(`${backendUrl}/api/1/premium/capabilities`, () =>
    HttpResponse.json(mockPremiumCapabilitiesResponse, { status: 200 })),

];
