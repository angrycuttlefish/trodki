import { z } from 'zod';

export const PremiumStatusUpdateData = z.object({
  expired: z.boolean(),
  isPremiumActive: z.boolean(),
  reason: z.string().optional(),
});

export type PremiumStatusUpdateData = z.infer<typeof PremiumStatusUpdateData>;
