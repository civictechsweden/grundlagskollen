import data from '../data/changes.json';
import graph from '../data/document-graph.json';
import riksdagData from '../data/riksdag-index.json';
import benchmark from '../data/benchmark-report.json';
import patchData from '../data/version-patches.json';
import versionReport from '../data/version-report.json';
import './style.css';

const app = document.querySelector('#app');
const laws = (data.constitutions || []).filter((law) => law.sfs);
const lawById = Object.fromEntries((data.constitutions || []).map((law) => [law.id, law]));
const documentPayload = Object.fromEntries(((riksdagData.documents || [])).map((document) => [document.documentId, document]));
const changes = data.changes || [];
const proposals = data.proposals || [];
const proposalById = Object.fromEntries(proposals.map((proposal) => [proposal.proposalId, proposal]));
const patchByKey = patchData.patches || {};
const palette = { rf: 'mint', tf: 'amber', ygl: 'lilac', so: 'coral', ro: 'slate' };
const years = changes.map((item) => yearOf(item.date)).filter(Boolean);
const minYear = Math.min(1885, ...years);
const maxYear = Math.max(2026, ...years);
const state = {
  year: maxYear,
  law: 'all',
  query: '',
  selectedChange: changes.find((item) => item.sfs === '2022:1600')?.id || changes[0]?.id,
  selectedProposal: proposals.find((item) => item.status === 'rejected')?.proposalId || proposals[0]?.proposalId,
};

function yearOf(value) {
  const match = String(value || '').match(/^(\d{4})/);
  return match ? Number(match[1]) : null;
}

function escapeHTML(value = '') {
  return String(value).replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;').replaceAll('"', '&quot;').replaceAll("'", '&#039;');
}

function formatDate(value, fallback = 'Datum saknas') {
  if (!value) return fallback;
  if (/^\d{4}$/.test(String(value))) return String(value);
  const date = new Date(value);
  return Number.isNaN(date.valueOf()) ? value : new Intl.DateTimeFormat('sv-SE', { day: 'numeric', month: 'long', year: 'numeric' }).format(date);
}

function formatShortDate(value) {
  if (!value) return '—';
  if (/^\d{4}$/.test(String(value))) return String(value);
  const date = new Date(value);
  return Number.isNaN(date.valueOf()) ? value : new Intl.DateTimeFormat('sv-SE', { day: 'numeric', month: 'short', year: 'numeric' }).format(date);
}

function daysUntil(value) {
  if (!value) return null;
  const target = new Date(`${value}T00:00:00`);
  const today = new Date();
  target.setHours(0, 0, 0, 0); today.setHours(0, 0, 0, 0);
  return Math.ceil((target - today) / 86400000);
}

function externalLink(url, label, className = 'source-link') {
  return url ? `<a class="${className}" href="${escapeHTML(url)}" target="_blank" rel="noreferrer">${escapeHTML(label)} ↗</a>` : '';
}

function badge(label, tone = 'neutral') {
  return `<span class="status-badge status-${tone}">${escapeHTML(label)}</span>`;
}

function lawPill(id) {
  const law = lawById[id];
  return law ? `<span class="law-pill law-${palette[id] || 'slate'}">${escapeHTML(law.short)}</span>` : '';
}

function statusTone(status) {
  return { adopted: 'confirmed', rejected: 'aborted', pending: 'pending', unresolved: 'neutral' }[status] || 'neutral';
}

function statusLabel(status) {
  return { adopted: 'antagen', rejected: 'förkastad', pending: 'vilande nu', unresolved: 'oklar' }[status] || status || 'kandidat';
}

function docFor(id) {
  return documentPayload[id] || {};
}

function docUrl(id) {
  const document = docFor(id);
  return document.documentUrl || `https://data.riksdagen.se/dokument/${id}`;
}

function decisionRefs(id, kind) {
  return (docFor(id).structuredReferences || []).filter((ref) => String(ref.ref_dok_typ || '').toLowerCase() === kind).map((ref) => `${ref.ref_dok_rm}:${ref.ref_dok_bet}`.replaceAll(' ', ''));
}

function renderHeader() {
  return `<header class="topbar"><a class="brand" href="#top"><span class="brand-mark">§</span><span>grundlags<span>monitor</span></span></a><nav class="topnav" aria-label="Huvudnavigation"><a href="#queue">På vänt</a><a href="#timeline">Tidslinje</a><a href="#decisions">Beslut</a><a href="#archive">SFS-arkiv</a><a href="#method">Metod</a></nav><div class="top-meta"><span class="live-dot"></span> Synkad ${formatShortDate(data.generatedAt)}</div></header>`;
}

function renderHero() {
  const election = data.election?.nextDate;
  const remaining = daysUntil(election);
  const adopted = proposals.filter((item) => item.status === 'adopted').length;
  return `<section class="hero" id="top"><div class="hero-copy"><div class="eyebrow">Öppen rättsdata · beslut → SFS → version</div><h1>Grundlagen ändras<br><em>inte i det tysta.</em></h1><p class="hero-intro">En spårbar tidsmaskin för Sveriges fyra grundlagar. Följ det vilande beslutet, se den slutliga behandlingen och öppna varje källa som binder ihop historien.</p><div class="hero-actions"><a class="button button-light" href="#timeline">Dra i tidslinjen ↓</a><a class="text-action" href="#method">Läs metoden ↗</a></div></div><div class="hero-visual"><div class="orbit orbit-one"></div><div class="orbit orbit-two"></div><div class="hero-card hero-card-main"><span class="card-kicker">Nästa val mellan besluten</span><strong>${formatDate(election)}</strong><span class="countdown">${remaining !== null && remaining >= 0 ? `${remaining} dagar kvar` : 'datum passerat'}</span></div><div class="hero-card hero-card-side"><span class="card-kicker">Vilande nu</span><strong>${data.pending?.length || 0}</strong><span>ärenden i den explicita kön</span></div><div class="hero-stamp">RF<br>TF<br>YGL<br>SO</div></div></section><section class="stats-shell" aria-label="Nyckeltal"><article class="stat-card stat-accent"><span class="stat-label">På vänt</span><strong>${data.pending?.length || 0}</strong><span class="stat-note">första beslutet finns</span></article><article class="stat-card"><span class="stat-label">Slutligt antagna</span><strong>${adopted}</strong><span class="stat-note">parlamentariskt beslut</span></article><article class="stat-card stat-warm"><span class="stat-label">Slutligt förkastade</span><strong>${proposals.filter((item) => item.status === 'rejected').length}</strong><span class="stat-note">uttrycklig signal</span></article><article class="stat-card stat-yellow"><span class="stat-label">SFS-poster</span><strong>${changes.length}</strong><span class="stat-note">${benchmark.metrics?.matched_to_sfs || 0} kopplade till beslut</span></article></section>`;
}

function renderMilestone(proposal) {
  const first = proposal.firstDecision || {};
  const final = proposal.finalDecision;
  const election = data.election?.nextDate;
  return `<div class="milestone-rail"><div class="milestone done"><span class="milestone-dot"></span><div><small>Första beslutet · vilande</small><strong>${formatShortDate(first.date)}</strong><span>${escapeHTML(first.documentId || 'Riksdagen')}</span></div></div><div class="milestone next"><span class="milestone-dot"></span><div><small>Val mellan besluten</small><strong>${formatShortDate(election)}</strong><span class="accent-text">${daysUntil(election) >= 0 ? `${daysUntil(election)} dagar kvar` : 'valet passerat'}</span></div></div><div class="milestone ${final ? 'done' : 'future'}"><span class="milestone-dot"></span><div><small>Andra beslutet</small><strong>${final ? formatShortDate(final.date) : 'inte hittat'}</strong><span>${final ? statusLabel(final.status) : 'samma lydelse krävs'}</span></div></div></div>`;
}

function renderQueueCard(proposal) {
  const first = proposal.firstDecision || {};
  const doc = docFor(first.documentId);
  const affected = proposal.constitutionIds?.length ? proposal.constitutionIds : doc.constitutionIds || [];
  return `<article class="queue-card"><div class="queue-copy"><div class="case-topline">${badge('VILANDE NU', 'pending')}<span class="law-stack">${affected.map(lawPill).join('')}</span><span class="case-id">${escapeHTML(first.documentId || proposal.proposalId)}</span></div><h3>${escapeHTML(proposal.title)}</h3><p>${escapeHTML(doc.title && doc.title !== proposal.title ? doc.title : 'Första beslutet är belagt; något slutligt beslut visas bara när det kan kopplas till källan.')}</p><div class="case-footer">${externalLink(first.documentUrl || docUrl(first.documentId), 'Första dokumentet')}${(first.propositionReferences || []).slice(0, 2).map((ref) => `<span class="ref-chip">${escapeHTML(ref.value)}</span>`).join('')}</div></div><div class="queue-side ${palette[proposal.constitutionIds?.[0]] || 'mint'}">${renderMilestone(proposal)}<button class="small-action" data-proposal="${escapeHTML(proposal.proposalId)}">Öppna beslutsgraf →</button></div></article>`;
}

function renderQueue() {
  const queue = data.pending || proposals.filter((item) => item.status === 'pending');
  return `<section class="section" id="queue"><div class="section-heading"><div><div class="eyebrow">01 / Nu</div><h2>Det som väntar<br><em>på väljarna.</em></h2></div><p>En grundlagsändring kräver två likalydande riksdagsbeslut med ett allmänt val emellan. Kön är en explicit, källbelagd status och blandas inte ihop med historiska luckor.</p></div><div class="queue-list">${queue.map(renderQueueCard).join('') || '<p class="empty-state">Ingen explicit kö i senaste snapshot.</p>'}</div><div class="info-band"><strong>Frånvaro är inte förkastelse.</strong><span>Om ett senare beslut inte hittas blir ärendet <em>okänt</em> i stället för automatiskt avbrutet.</span></div></section>`;
}

function timelineDots(law) {
  return changes.filter((item) => item.constitutionId === law.id && yearOf(item.date)).map((item) => {
    const left = ((yearOf(item.date) - minYear) / (maxYear - minYear)) * 100;
    return `<button class="timeline-dot-button${state.selectedChange === item.id ? ' selected' : ''}" style="left:${Math.max(0, Math.min(100, left))}%" data-change="${escapeHTML(item.id)}" title="${escapeHTML(item.sfs)}"><span></span><b>${yearOf(item.date)}</b></button>`;
  }).join('');
}

function renderSelectedChange() {
  const item = changes.find((change) => change.id === state.selectedChange && (!yearOf(change.date) || yearOf(change.date) <= state.year)) || changes.find((change) => yearOf(change.date) <= state.year) || changes[0];
  if (!item) return '<aside class="detail-card empty-state">Inga SFS-händelser i detta läge.</aside>';
  const law = lawById[item.constitutionId] || {};
  const patch = patchByKey[`${item.constitutionId}:${item.sfs}`];
  const operations = item.operations || [];
  return `<aside class="detail-card"><div class="detail-top"><span class="eyebrow">Vald SFS-händelse</span>${badge('METADATA-PATCH', 'confirmed')}</div><div class="detail-law">${lawPill(item.constitutionId)}<span>${escapeHTML(law.title || '')}</span></div><h3>${escapeHTML(item.sfs)}</h3><p>${escapeHTML(item.description || item.title)}</p><dl class="metadata-list"><div><dt>Ikraft</dt><dd>${formatDate(item.date)}</dd></div><div><dt>Operationer</dt><dd>${operations.length ? operations.map((operation) => `${escapeHTML(operation.operationType)}${operation.chapter ? ` · ${escapeHTML(operation.chapter)}:${escapeHTML(operation.section || '')}` : ''}`).join('<br>') : 'okänd · behöver granskning'}</dd></div><div><dt>Förarbeten</dt><dd>${escapeHTML((item.preparatoryWorks || []).slice(0, 4).join(' · ') || 'saknas')}</dd></div></dl><div class="detail-actions">${externalLink(item.lawUrl, 'Öppna SFS-metadata', 'button button-dark')}${externalLink(item.versionUrl, 'Ferenda-version', 'button button-outline')}${patch ? externalLink(patch.path, 'Normaliserad diff', 'source-link') : ''}</div><small class="disclaimer">Operationen är en tolkning av SFS-metadata. Omtryck betyder inte att hela lagen ändrades.</small></aside>`;
}

function renderTimeline() {
  const visible = changes.filter((item) => yearOf(item.date) && yearOf(item.date) <= state.year).sort((a, b) => (b.date || '').localeCompare(a.date || ''));
  const ticks = [minYear, 1921, 1974, 1991, 2003, 2011, 2023, maxYear].filter((year, index, list) => year >= minYear && year <= maxYear && list.indexOf(year) === index);
  return `<section class="section timeline-section" id="timeline"><div class="section-heading"><div><div class="eyebrow">02 / Tid</div><h2>Flytta dig genom<br><em>grundlagsminnet.</em></h2></div><div class="timeline-caption"><strong>${state.year}</strong><span>${visible.length} daterade SFS-poster fram till året</span></div></div><div class="time-machine"><div class="slider-row"><span>${minYear}</span><input id="year-slider" type="range" min="${minYear}" max="${maxYear}" value="${state.year}" step="1" aria-label="Välj årtal"><span>${maxYear}</span></div><div class="timeline-years">${ticks.map((year) => `<span style="left:${((year - minYear) / (maxYear - minYear)) * 100}%">${year}</span>`).join('')}</div><div class="timeline-lanes">${laws.map((law) => `<div class="timeline-lane"><div class="lane-label">${lawPill(law.id)}<span>${escapeHTML(law.title)}</span></div><div class="lane-track"><div class="track-line"></div>${timelineDots(law)}</div></div>`).join('')}</div></div><div class="timeline-detail-grid"><div class="event-stream"><div class="subheading"><span>Händelser i läget</span><span>${visible.length} / ${changes.filter((item) => item.date).length}</span></div>${visible.slice(0, 10).map((item) => `<button class="event-row${state.selectedChange === item.id ? ' event-selected' : ''}" data-change="${escapeHTML(item.id)}"><span class="event-year">${yearOf(item.date)}</span>${lawPill(item.constitutionId)}<span class="event-main"><b>${escapeHTML(item.sfs)}</b><small>${escapeHTML(item.title)}</small></span><span class="event-arrow">↗</span></button>`).join('') || '<p class="empty-state">Dra reglaget åt höger för att visa händelser.</p>'}</div>${renderSelectedChange()}</div></section>`;
}

function renderDecisionNode(label, date, status, id, url) {
  return `<div class="decision-node"><span class="node-index">${escapeHTML(label)}</span><strong>${formatShortDate(date)}</strong><span>${badge(statusLabel(status), statusTone(status))}</span>${externalLink(url, 'Källa')}</div>`;
}

function renderDecisionGraph() {
  const selected = proposalById[state.selectedProposal] || proposals[0];
  if (!selected) return '';
  const first = selected.firstDecision || {};
  const final = selected.finalDecision;
  const firstDoc = docFor(first.documentId);
  const finalDoc = final ? docFor(final.documentId) : {};
  return `<section class="section decisions-section" id="decisions"><div class="section-heading"><div><div class="eyebrow">03 / Beslutsgraf</div><h2>Från förslag<br><em>till lag.</em></h2></div><p>KU:s betänkande är ett underlag. Grafen visar den faktiska första och slutliga beslutspunkten, dokumentreferenserna och eventuell SFS-länk separat.</p></div><div class="decision-layout"><div class="proposal-picker"><div class="subheading"><span>Ärenden</span><span>${proposals.length}</span></div>${proposals.filter((item) => ['pending', 'adopted', 'rejected', 'unresolved'].includes(item.status)).slice(0, 80).map((item) => `<button class="proposal-option${item.proposalId === selected.proposalId ? ' active' : ''}" data-proposal="${escapeHTML(item.proposalId)}"><span>${lawPill(item.constitutionIds?.[0])}</span><strong>${escapeHTML(item.title)}</strong><small>${escapeHTML(item.firstDecision?.documentId || '')} · ${statusLabel(item.status)}</small></button>`).join('')}</div><div class="decision-detail"><div class="decision-status">${badge(statusLabel(selected.status), statusTone(selected.status))}<span>${escapeHTML(selected.proposalId)}</span></div><h3>${escapeHTML(selected.title)}</h3><div class="decision-rail">${renderDecisionNode('01 · första', first.date, 'pending', first.documentId, first.documentUrl || docUrl(first.documentId))}<span class="rail-line"></span>${final ? renderDecisionNode('02 · slutligt', final.date, final.status, final.documentId, final.documentUrl || docUrl(final.documentId)) : `<div class="decision-node missing"><span class="node-index">02 · slutligt</span><strong>Ej hittat</strong><span>${badge('OKÄNT', 'neutral')}</span><small>Öppen fråga — inte förkastad</small></div>`}<span class="rail-line"></span><div class="decision-node sfs-node"><span class="node-index">03 · SFS</span><strong>${selected.sfsIds?.length ? selected.sfsIds.join(' · ') : 'Ingen match'}</strong><span>${badge(selected.sfsIds?.length ? 'PROMULGERAD' : 'SAKNAS', selected.sfsIds?.length ? 'confirmed' : 'neutral')}</span></div></div><div class="evidence-box"><div class="subheading"><span>Belägg i beslutstext</span><span>${(finalDoc.evidence || firstDoc.evidence || []).length}</span></div><p>${escapeHTML((finalDoc.evidence || firstDoc.evidence || ['Ingen textsignal sparad.'])[0])}</p><div class="evidence-links">${externalLink(first.documentUrl || docUrl(first.documentId), 'Första dokumentet')}${final ? externalLink(final.documentUrl || docUrl(final.documentId), 'Slutligt dokument') : ''}${(final ? decisionRefs(final.documentId, 'rskr') : []).map((ref) => `<span class="ref-chip">rskr ${escapeHTML(ref)}</span>`).join('')}</div></div></div></div></section>`;
}

function filteredChanges() {
  const query = state.query.trim().toLowerCase();
  return changes.filter((item) => {
    const lawMatch = state.law === 'all' || item.constitutionId === state.law;
    const yearMatch = !item.date || yearOf(item.date) <= state.year;
    const haystack = [item.sfs, item.title, item.description, ...(item.preparatoryWorks || []), ...(item.operations || []).map((operation) => operation.operationType)].join(' ').toLowerCase();
    return lawMatch && yearMatch && (!query || haystack.includes(query));
  });
}

function renderArchive() {
  const items = filteredChanges();
  return `<section class="section archive-section" id="archive"><div class="section-heading"><div><div class="eyebrow">04 / Källregister</div><h2>SFS-<br><em>arkivet.</em></h2></div><p>Varje post kommer från Ferendas metadataindex. Operationer är konservativa tolkningar av ersatta/införda avsnitt och lämnar okända specialfall synliga.</p></div><div class="archive-toolbar"><div class="law-tabs"><button class="${state.law === 'all' ? 'active' : ''}" data-law="all">Alla <b>${changes.length}</b></button>${laws.map((law) => `<button class="${state.law === law.id ? 'active' : ''}" data-law="${law.id}">${escapeHTML(law.short)} <b>${changes.filter((item) => item.constitutionId === law.id).length}</b></button>`).join('')}</div><label class="search-box"><span>⌕</span><input id="archive-search" type="search" value="${escapeHTML(state.query)}" placeholder="Sök SFS, avsnitt eller förarbete"></label></div><div class="archive-header"><span>År</span><span>Lag</span><span>Ändring</span><span>Operation</span><span>Ikraft</span></div><div class="archive-list">${items.slice(0, 100).map((item) => `<button class="archive-row" data-change="${escapeHTML(item.id)}"><span class="archive-year">${yearOf(item.date) || '—'}</span><span>${lawPill(item.constitutionId)}</span><span class="archive-change"><b>${escapeHTML(item.sfs)}</b><strong>${escapeHTML(item.title)}</strong><small>${escapeHTML((item.preparatoryWorks || []).slice(0, 2).join(' · '))}</small></span><span class="operation-label">${escapeHTML(item.operations?.[0]?.operationType || 'needs review')}</span><span class="archive-date">${formatShortDate(item.date)}</span></button>`).join('') || '<p class="empty-state">Inga träffar.</p>'}</div><div class="archive-footer"><span>Visar ${Math.min(items.length, 100)} av ${items.length}</span><span>Ändra år eller sök för att följa en annan bana.</span></div></section>`;
}

function renderQuality() {
  const metrics = benchmark.metrics || {};
  const regression = benchmark.regressions || [];
  return `<section class="section quality-section" id="quality"><div class="section-heading"><div><div class="eyebrow">05 / Kontroll</div><h2>Vad vet vi<br><em>egentligen?</em></h2></div><p>Regressionerna är fasta kontrollpunkter. Täckningsmåtten visar vad körningen hittade; de gör inte en ändlig lista till bevis på fullständig historia.</p></div><div class="quality-grid"><div class="quality-card"><div class="subheading"><span>Regressionsfall</span><strong>${metrics.regression_passed || 0}/${metrics.regression_cases || 0}</strong></div><div class="regression-list">${regression.map((item) => `<div class="regression-row"><span class="check ${item.passed ? 'pass' : 'fail'}">${item.passed ? '✓' : '!'}</span><span><b>${escapeHTML(item.id)}</b><small>${item.checks.filter((check) => check.passed).length}/${item.checks.length} kontroller</small></span></div>`).join('')}</div></div><div class="quality-card metric-card"><div><span>Dokumentgraf</span><strong>${graph.nodes?.length || 0}</strong><small>noder · ${graph.edges?.length || 0} spårbara kanter</small></div><div><span>Omatchade SFS</span><strong>${metrics.orphan_sfs || 0}</strong><small>kräver vidare koppling</small></div><div><span>Antagna utan SFS</span><strong>${metrics.adopted_without_sfs_match || 0}</strong><small>QA-fråga, inte nödvändigt fel</small></div></div></div><div class="quality-note"><strong>Ferenda</strong><span>${metrics?.matched_to_sfs || 0} SFS-poster matchas via förarbeten. Versionsexperimentet kontrollerade ${benchmark.ferenda_snapshots?.checked || 0} referenssidor; fulltext-applicering är <em>${versionReport.summary?.fullTextApplication || 'not_attempted'}</em>, så inga exakta textmatchningar påstås.</span></div></section>`;
}

function renderMethod() {
  const summary = versionReport.summary || {};
  const metrics = benchmark.metrics || {};
  return `<section class="section method-section" id="method"><div class="method-intro"><div class="eyebrow">06 / Metod & begränsningar</div><h2>Spårbart hela vägen<br><em>till källan.</em></h2><p>Datamodellen håller isär proposition, KU-underlag, kammarbeslut, protokoll, riksdagsskrivelse och SFS. Riksdagen upptäcker beslut; Ferenda levererar ett tekniskt SFS-index och en benchmark.</p></div><div class="method-cards"><article><span>01</span><h3>Riksdagens öppna data</h3><p>${data.coverage?.documentsFetched || 0} relevanta dokument hämtades från ${data.coverage?.modernCandidateDocuments || 0} kandidater. Textsignaler och strukturerade referenser sparas med provenance.</p>${externalLink(data.sources?.riksdagOpenData, 'Öppna Riksdagens data')}</article><article><span>02</span><h3>SFS som patch</h3><p>${summary.fullTextApplication === 'not_attempted' ? 'Metadata-operationer är genererade; fulltextmotorn väntar på säkra baslydelser och ersättningstext.' : 'Historiska lydelser är genererade.'} Omtryck tolkas inte som att hela lagen ändrades.</p>${externalLink(data.sources?.ferendaOpenApi, 'Öppna Ferendas API')}</article><article><span>03</span><h3>Kontrollpunkter</h3><p>${benchmark.metrics?.regression_passed || 0} av ${benchmark.metrics?.regression_cases || 0} fasta regressionsfall passerar. Se rapporterna för varje kontroll och källa.</p>${externalLink('/DATA_BENCHMARK.md', 'Läs benchmarkrapport')}</article></div><div class="method-metrics"><div><span>Förslag</span><strong>${proposals.length}</strong><small>first/final-modell</small></div><div><span>SFS-händelser</span><strong>${changes.length}</strong><small>metadataindex</small></div><div><span>Referenssidor</span><strong>${summary.fetchedVersions || 0}</strong><small>Ferenda hämtade</small></div><div><span>Okända</span><strong>${metrics.unresolved || 0}</strong><small>inte automatiskt fallna</small></div></div><p class="method-disclaimer">Källhierarki: officiell SFS och Riksdagsdokument först, Riksdagens metadata därefter, Ferenda som teknisk källa/validator. Läs <a href="/VERSIONING_REPORT.md">VERSIONING_REPORT.md</a> och <a href="/DATA_BENCHMARK.md">DATA_BENCHMARK.md</a>.</p></section><footer class="footer"><span>GRUNDLAGSMONITOR / REPRODUCERBAR PROTOTYP</span><span>${formatShortDate(data.generatedAt)} · ${changes.length} SFS-poster · ${proposals.length} beslutskedjor</span></footer>`;
}

function render() {
  app.innerHTML = `${renderHeader()}<main>${renderHero()}${renderQueue()}${renderTimeline()}${renderDecisionGraph()}${renderArchive()}${renderQuality()}${renderMethod()}</main>`;
}

app.addEventListener('click', (event) => {
  const proposal = event.target.closest('[data-proposal]');
  if (proposal) {
    event.preventDefault();
    state.selectedProposal = proposal.dataset.proposal;
    render();
    document.querySelector('#decisions')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    return;
  }
  const change = event.target.closest('[data-change]');
  if (change) {
    event.preventDefault();
    state.selectedChange = change.dataset.change;
    render();
    document.querySelector('#timeline')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    return;
  }
  const law = event.target.closest('[data-law]');
  if (law) {
    event.preventDefault();
    state.law = law.dataset.law;
    render();
    document.querySelector('#archive')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }
});

app.addEventListener('input', (event) => {
  if (event.target.id === 'year-slider') {
    state.year = Number(event.target.value);
    render();
    document.querySelector('#timeline')?.scrollIntoView({ behavior: 'auto', block: 'start' });
  }
  if (event.target.id === 'archive-search') {
    state.query = event.target.value;
    render();
    const input = document.querySelector('#archive-search');
    input?.focus();
    input?.setSelectionRange(state.query.length, state.query.length);
  }
});

render();
