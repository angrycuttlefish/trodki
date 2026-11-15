import { bigNumberify } from '@rotki/common';
import { describe, expect, it } from 'vitest';
import { HyperliquidPerpPositionsSchema } from '@/modules/staking/staking-types';

describe('modules/staking/hyperliquid/HyperliquidPerpPositionsSchema', () => {
  it('should parse the camel cased positions response, with a null liquidation price', () => {
    const parsed = HyperliquidPerpPositionsSchema.parse({
      accounts: {
        '0xAbc': [{
          dex: 'xyz',
          entryPrice: '182.46',
          fundingSinceOpen: '0.025508',
          leverage: '3',
          leverageType: 'cross',
          liquidationPrice: null,
          marginUsed: '3.625306',
          market: 'xyz:NVDA',
          markPrice: '159.94',
          positionValue: '10.87592',
          returnOnEquity: '-0.37',
          side: 'long',
          size: '0.068',
          unrealizedPnl: '-1.53136',
        }],
      },
      failed: [],
    });

    const [position] = parsed.accounts['0xAbc'];
    expect(position.unrealizedPnl).toEqual(bigNumberify('-1.53136'));
    expect(position.liquidationPrice).toBeNull();
    expect(position.dex).toBe('xyz');
  });
});
