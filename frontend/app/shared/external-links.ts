const DOCS_SUBFOLDER = !import.meta.env?.DEV ? '' : 'latest/';
/**
 * trodki has no vendor site: product and support links point at the trodki repository, while
 * usage-guide links still open upstream rotki's documentation (user-initiated, sends no data).
 */
const TRODKI_URL = 'https://github.com/angrycuttlefish/trodki';
const OLD_DOCS_BASE_URL = 'https://rotki.readthedocs.io/en/stable/';
const DOCS_BASE_URL = `https://docs.rotki.com/${DOCS_SUBFOLDER}`;
const USAGE_GUIDE_URL = `${DOCS_BASE_URL}usage-guides/`;
const CONTRIBUTE_URL = `${DOCS_BASE_URL}contribution-guides/`;
const GITHUB_BASE_URL = `${TRODKI_URL}/`;

/**
 * Excluded from the link checker because automated requests are rejected.
 */
export const TWITTER_URL = TRODKI_URL;

export const SUPPORT_EMAIL = '';

/**
 * Not reachable by the link checker: it needs authentication, so it always answers 403 and
 * redirects to the register page.
 */
export const etherscanLink = 'https://etherscan.io/myapikey';

export const heliusLink = 'https://dev.helius.xyz/dashboard/app';

export const blockscoutLink = 'https://dev.blockscout.com/';

export const externalLinks = {
  dockerSessionAuth: `${DOCS_BASE_URL}requirement-and-installation/docker#session-authentication`,
  integrations: `${TRODKI_URL}#readme`,
  premium: `${TRODKI_URL}#readme`,
  premiumDevices: `${TRODKI_URL}#readme`,
  sponsor: `${TRODKI_URL}#readme`,
  manageSubscriptions: `${TRODKI_URL}#readme`,
  usageGuide: USAGE_GUIDE_URL,
  usageGuideSection: {
    addingAnExchange: `${USAGE_GUIDE_URL}integrations/exchange-keys#exchanges-api-keys`,
    theGraphApiKey: `${USAGE_GUIDE_URL}integrations/external-services#the-graph`,
    gnosisPayKey: `${USAGE_GUIDE_URL}integrations/external-services#gnosis-pay`,
    importBlockchainAccounts: `${USAGE_GUIDE_URL}portfolio/accounts#import-and-export-blockchain-accounts-csv`,
    importAddressBook: `${USAGE_GUIDE_URL}data-management/address-book#importing-address-book-names-csv`,
    solanaTokenMigration: 'https://github.com/rotki/rotki/releases/tag/v1.40.0',
    eventTypes: `${USAGE_GUIDE_URL}tax-accounting/event-types`,
    accountingRules: `${USAGE_GUIDE_URL}tax-accounting/accounting-rules`,
    accountingRuleCountCostBasisPnl: `${USAGE_GUIDE_URL}tax-accounting/accounting-rules#count-cost-basis-pnl`,
    accountingTreatmentSwap: `${USAGE_GUIDE_URL}tax-accounting/accounting-rules#accounting-treatment-swap`,
    accountingTreatmentBasisTransfer: `${USAGE_GUIDE_URL}tax-accounting/accounting-rules#accounting-treatment-basis-transfer`,
  },
  coingeckoAsset: `https://www.coingecko.com/en/coins/$symbol`,
  cryptocompareAsset: `https://www.cryptocompare.com/coins/$symbol/overview`,
  contribute: CONTRIBUTE_URL,
  contributeSection: {
    coingecko: `${CONTRIBUTE_URL}contribute-as-developer#get-coingecko-asset-identifier`,
    cryptocompare: `${CONTRIBUTE_URL}contribute-as-developer#get-cryptocompare-asset-identifier`,
    language: `${CONTRIBUTE_URL}contribute-as-developer#add-a-new-language-or-translation`,
  },
  faq: `${DOCS_BASE_URL}faq`,
  changeLog: `${OLD_DOCS_BASE_URL}changelog.html`,
  discord: `${GITHUB_BASE_URL}issues`,
  github: GITHUB_BASE_URL,
  githubIssues: `${GITHUB_BASE_URL}issues`,
  githubNewIssue: `${GITHUB_BASE_URL}issues/new/choose`,
  githubNewBugReport: `${GITHUB_BASE_URL}issues/new?template=bug_report.md`,
  gmailCompose: 'https://mail.google.com/mail/?view=cm',
  releases: `${GITHUB_BASE_URL}releases`,
  releasesVersion: `${GITHUB_BASE_URL}releases/tag/v$version`,
  metamaskDownload: 'https://metamask.io/download/',
  openSeaApiKeyReference: 'https://docs.opensea.io/reference/api-keys#how-do-i-get-an-api-key',
  nftWarning: 'https://medium.com/@alxlpsc/critical-privacy-vulnerability-getting-exposed-by-metamask-693c63c2ce94',
  binanceCsvExport: 'https://www.binance.com/en/my/wallet/history',
  migrationAssistant: 'https://rotki.github.io/migration-assistant/',
  applyTheGraphApiKey: 'https://thegraph.com/studio/apikeys/',
  liquityTotalCollateralRatioDoc: 'https://docs.liquity.org/liquity-v1/faq/recovery-mode#what-is-the-total-collateral-ratio',
  coingeckoApiKey: 'https://www.coingecko.com/en/api/pricing',
  defillamaApiKey: 'https://defillama.com/pro-api',
  alchemyApiKey: 'https://docs.alchemy.com/reference/api-overview',
  moralisApiKey: 'https://docs.moralis.com/web3-data-api/evm/get-your-api-key',
  birdeyeApiKey: 'https://data.birdeye.so/docs/authentication',
  beaconChainApiKey: 'https://beaconcha.in/user/settings',
};
