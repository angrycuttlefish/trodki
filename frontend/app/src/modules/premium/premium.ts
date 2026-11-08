import { type Component, defineComponent, h } from 'vue';
import LocalFeaturePending from '@/modules/premium/LocalFeaturePending.vue';

/**
 * Upstream mounts these views from a premium bundle downloaded from rotki's servers. trodki
 * never loads remote code, so each is a local placeholder until it is rebuilt (roadmap phase 3).
 */
function pending(feature: string): Component {
  return defineComponent({
    name: `Local${feature.replaceAll(' ', '')}`,
    setup: () => (): ReturnType<typeof h> => h(LocalFeaturePending, { feature }),
  });
}

export const PremiumStatistics = pending('Statistics graphs');

export const EthStaking = pending('ETH staking');

export const AssetAmountAndValueOverTime = pending('Asset amount and value over time');

export const ThemeManager = pending('Theme manager');
