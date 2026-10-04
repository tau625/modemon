// marker -> chunk matrix, to pin which source module lives in which chunk
const fs = require('fs');
const path = require('path');
const D = 'E:/02_Installers/DailyApps/Modex-MH-Agent-RE/beauty';
const MARKS = {
  'App.tsx (disclaimer gate)': 'mhagent_disclaimer_accepted',
  'useTheme.tsx': 'MH Agent-theme',
  'accessMode.ts': 'modex-access-mode-changed',
  'accountAccess.ts': 'AccountRequestError',
  'clientConfig.ts': '/api/client-config',
  'Account.tsx': 'native-wallet',
  'chatDraft.ts': 'modex.chat.draft.v1:',
  'chatOutbox.ts': 'chat-outbox:v1:',
  'editorUndo.ts': 'modex.editor.undo:',
  'editorImage.ts': 'modex-image-request:',
  'nativeCheckout.ts': 'modex-native-checkout:',
  'MarkdownViewer.tsx (react-markdown)': 'rehype-katex',
  'ArtifactLibrary.tsx': 'beginnerHint:`建议优先查看`',
  'ChatWorkbench.tsx': 'chat-mode-option',
  'WorkflowDetail.tsx': 'auto-workflow-actions',
  'CheckpointModal.tsx': 'assets_resolve',
  'LogStream.tsx': 'log-stream',
  'ScoreChart.tsx': '审稿分数曲线',
  'LatexEditor.tsx': '/ai-agent-check',
  'NewWorkflow.tsx': 'comp_cumcm',
  'Settings.tsx': 'model_context_policies',
  'Dashboard.tsx': 'workflow-card',
  'ArtifactViewer.tsx': 'artifact-context/prompt/build',
  'PatchReviewDialog.tsx': 'patch-review',
  'AccountModelCatalog.tsx': 'model-catalog-row',
  'newApiWallet.tsx': 'native-usage-tabs',
  'AccountMessagesInference.tsx': '/api/account/messages',
  'useWebSocket.ts': 'handleChatEvent',
  'workflowStore.ts': 'fetchWorkflows',
  'useAccessMode.tsx': '/api/account/access-mode',
  'useCheckpointSession.ts': 'checkpoints/current',
  'useWorkflowSteps.ts': 'resolve-steps',
  'chatStore.ts': 'fetchRunEvents',
  'ProposalCard.tsx': 'chat-card-body',
  'StepCard.tsx': 'recovery_phase',
  'ArtifactCollection.tsx': 'collectionEndpoint',
  'useTailScroll.ts': 'useTailScroll',
  'scrollFollow.ts': 'scrollFollow',
  'effort.ts': 'xhigh',
  'modelDiscovery.ts': 'settings/models/discover',
  'accountModelSelection.ts': 'account-model',
  'WorkflowPayerBadge.tsx': 'payer',
  'LicenseGate.tsx': '/api/license/verify',
  'recharts (vendor)': 'recharts-surface',
  'immer (vendor, recharts dep)': 'immer-nothing',
  'redux toolkit (vendor, recharts dep)': 'listenerMiddleware',
  'react-router (vendor)': 'reactrouter.com/en/main',
  'KaTeX (vendor)': 'katex',
  'react-markdown (vendor)': 'hast-util-to-jsx-runtime',
};
const chs = fs.readdirSync(D).filter(f => f.endsWith('.pretty.js'));
const cache = new Map();
for (const c of chs) cache.set(c, fs.readFileSync(path.join(D, c), 'utf8'));
const rows = [];
for (const [name, m] of Object.entries(MARKS)) {
  const hits = chs.filter(c => cache.get(c).includes(m));
  rows.push(`${name}\t${hits.length ? hits.map(h => h.replace('.pretty.js', '')).join(' | ') : '(NOT FOUND)'}`);
}
fs.writeFileSync('E:/02_Installers/DailyApps/Modex-MH-Agent-RE/reports/_fx/homes.tsv', rows.join('\n'), 'utf8');
console.log(rows.join('\n'));
