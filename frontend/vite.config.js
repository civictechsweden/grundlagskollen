import { defineConfig } from 'vite';
import tailwindcss from '@tailwindcss/vite';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

const datasetPath = fileURLToPath(new URL('../data/changes.json', import.meta.url));
const datasetModule = '\0virtual:grundlagsmonitor-data';

// Keep the complete legal evidence in the source dataset. Ship only fields
// used by the interface, rather than every graph edge and parser excerpt.
function frontendDataset() {
  const data = JSON.parse(readFileSync(datasetPath, 'utf8'));
  const pick = (value, keys) => value && Object.fromEntries(keys.filter((key) => key in value).map((key) => [key, value[key]]));
  return {
    ...pick(data, ['constitutions', 'election', 'generatedAt', 'currentRefreshedAt', 'historicalSnapshotAt', 'sources']),
    changes: data.changes.map((change) => ({
      ...pick(change, ['sfs', 'constitutionId', 'lawUrl', 'comparisonUrl', 'printedVersionUrl']),
      effectiveDate: change.metadata?.ikraft || change.date || null,
    })),
    proposals: data.proposals.map((proposal) => ({
      ...pick(proposal, ['proposalId', 'title', 'sourceText', 'status', 'constitutionIds', 'sfsIds', 'parliamentaryProgress', 'match']),
      ...Object.fromEntries(['firstDecision', 'finalDecision', 'nextDecision'].map((field) => [field, pick(proposal[field], ['documentId', 'date', 'documentUrl', 'parliamentaryProgress'])])),
    })),
  };
}

export default defineConfig({
  plugins: [tailwindcss(), {
    name: 'grundlagsmonitor-data',
    resolveId(id) { if (id === 'virtual:grundlagsmonitor-data') return datasetModule; },
    load(id) {
      if (id !== datasetModule) return;
      this.addWatchFile(datasetPath);
      return `export default ${JSON.stringify(frontendDataset())};`;
    },
    handleHotUpdate({ file, server }) {
      if (file !== datasetPath) return;
      const module = server.moduleGraph.getModuleById(datasetModule);
      if (module) server.moduleGraph.invalidateModule(module);
      server.ws.send({ type: 'full-reload' });
      return [];
    },
  }],
});
