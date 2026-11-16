<script setup lang="ts">
import type { LogoProps } from '@rotki/ui-library';

/**
 * The trodki mark: an original troll head with the word "trodki" underneath.
 *
 * Replaces upstream's robin (`RuiLogo`). Same props as before so every caller keeps working:
 * `size` is the mark's height in rem, `text` shows the word (on by default; the collapsed
 * sidebar turns it off). `uniqueKey` is accepted for compatibility and unused: the SVG has no
 * ids that could clash when several logos are on screen.
 */
defineOptions({
  inheritAttrs: false,
});

const { text = true, size = 2 } = defineProps<{
  // eslint-disable-next-line vue/no-unused-properties -- kept so existing callers stay valid
  uniqueKey?: LogoProps['uniqueKey'];
  text?: LogoProps['text'];
  size?: LogoProps['size'];
}>();

const { t } = useI18n({ useScope: 'global' });

const markSize = computed<string>(() => `${size}rem`);
const wordSize = computed<string>(() => `${Math.max(Number(size) * 0.32, 0.75)}rem`);
</script>

<template>
  <div
    v-bind="$attrs"
    class="inline-flex flex-col items-center"
    data-testid="trodki-logo"
  >
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 64 64"
      role="img"
      aria-label="trodki"
      :style="{ width: markSize, height: markSize }"
    >
      <path
        d="M10 30 L1 19 L15 25 Z"
        fill="#5f9c46"
        stroke="#2f5523"
        stroke-width="1.5"
        stroke-linejoin="round"
      />
      <path
        d="M54 30 L63 19 L49 25 Z"
        fill="#5f9c46"
        stroke="#2f5523"
        stroke-width="1.5"
        stroke-linejoin="round"
      />
      <path
        d="M24 13 C22 5 28 2 32 8 C34 1 41 2 40 10 C44 6 48 9 44 14 Z"
        fill="#c8552d"
        stroke="#7a2f15"
        stroke-width="1.5"
        stroke-linejoin="round"
      />
      <path
        d="M12 30 C12 16 21 11 32 11 C43 11 52 16 52 30 C52 46 44 58 32 58 C20 58 12 46 12 30 Z"
        fill="#74b356"
        stroke="#2f5523"
        stroke-width="2"
      />
      <path
        d="M19 24 Q24 20 29 24"
        fill="none"
        stroke="#2f5523"
        stroke-width="2.2"
        stroke-linecap="round"
      />
      <path
        d="M35 24 Q40 20 45 24"
        fill="none"
        stroke="#2f5523"
        stroke-width="2.2"
        stroke-linecap="round"
      />
      <circle
        cx="24"
        cy="29"
        r="4.2"
        fill="#ffffff"
        stroke="#2f5523"
        stroke-width="1.2"
      />
      <circle
        cx="40"
        cy="29"
        r="4.2"
        fill="#ffffff"
        stroke="#2f5523"
        stroke-width="1.2"
      />
      <circle
        cx="25"
        cy="30"
        r="1.9"
        fill="#1d2a17"
      />
      <circle
        cx="39"
        cy="30"
        r="1.9"
        fill="#1d2a17"
      />
      <ellipse
        cx="32"
        cy="38"
        rx="6.5"
        ry="5"
        fill="#5f9c46"
        stroke="#2f5523"
        stroke-width="1.5"
      />
      <path
        d="M21 46 Q32 54 43 46"
        fill="#3a1f14"
        stroke="#2f5523"
        stroke-width="1.5"
        stroke-linejoin="round"
      />
      <path
        d="M24.5 47.6 L26 43.5 L27.6 48.9 Z"
        fill="#f4efe2"
        stroke="#2f5523"
        stroke-width="0.8"
        stroke-linejoin="round"
      />
      <path
        d="M39.5 47.6 L38 43.5 L36.4 48.9 Z"
        fill="#f4efe2"
        stroke="#2f5523"
        stroke-width="0.8"
        stroke-linejoin="round"
      />
    </svg>
    <span
      v-if="text"
      class="font-bold tracking-wide leading-none mt-1 text-rui-text"
      :style="{ fontSize: wordSize }"
    >
      {{ t('app.name') }}
    </span>
  </div>
</template>
