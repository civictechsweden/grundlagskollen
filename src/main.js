import data from '../data/changes.json';
import patchData from '../data/version-patches.json';
import benchmark from '../data/benchmark-report.json';
import versionReport from '../data/version-report.json';
import './style.css';

const app = document.querySelector('#app');
const laws = data.constitutions.filter((law) => law.sfs);
const lawById = Object.fromEntries(data.constitutions.map((law) => [law.id, law]));
const patchByKey = patchData.patches || {};
const state = {
  law: 'all',
  query: '',
  year: Math.max(...data.changes.filter((item) => item.date).map((item) => Number(item.date.slice(0, 4))), 2026),
  selected: data.pending[2]?.id || data.changes.find((item) => item.date)?.id,
};

const palette = { rf: 'mint', tf: 'amber', ygl: 'lilac', so: 'coral', ro: 'slate' };
const escapeHTML = (value = '') => String(value).replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;').replaceAll('"', '&quot;').replaceAll("'", '&#039;');
const formatDate = (value, fallback = 'Datum saknas') => {
  if (!value) return fallback;
  if (/^\d{4}$/.test(String(value))) return String(value);
  const date = new Date(value);
  return Number.isNaN(date.valueOf()) ? value : new Intl.DateTimeFormat('sv-SE', { day: 'numeric', month: 'long', year: 'numeric' }).format(date);
};
const formatShortDate = (value) => {
  if (!value) return '—';
  if (/^\d{4}$/.test(String(value))) return String(value);
  const date = new Date(value);
  return Number.isNaN(date.valueOf()) ? value : new Intl.DateTimeFormat('sv-SE', { day: 'numeric', month: 'short', year: 'numeric' }).format(date);
};
const yearOf = (value) => Number.parseInt(String(value || '').slice(0, 4), 10) || null;
const daysUntil = (value) => {
  if (!value) return null;
  const target = new Date(`${value}T00:00:00`);
  const today = new Date();
  target.setHours(0, 0, 0, 0); today.setHours(0, 0, 0, 0);
  return Math.ceil((target - today) / 86400000);
};
const link = (url, label, className = '') => url ? `<a class="${className}" href="${escapeHTML(url)}" target="_blank" rel="noreferrer">${escapeHTML(label)} ↗</a>` : '';
const sourceLinks = (urls = []) => urls.map((url, index) => link(url, ['källa', 'betänkande', 'proposition'][index] || 'underlag', 'source-link')).join('');
const statusBadge = (label, tone = 'neutral') => `<span class="status-badge status-${tone}">${escapeHTML(label)}</span>`;
const eventYear = (item) => yearOf(item.date || item.finalDecisionDate || item.firstDecisionDate);
const datedChanges = data.changes.filter((item) => item.date && yearOf(item.date));
const minYear = Math.min(...datedChanges.map(eventYear), 1954);
const maxYear = Math.max(state.year, 2026);

function renderTopbar() {
  return `<header class="topbar"><a class="brand" href="#top" aria-label="Grundlagsmonitor"><span class="brand-mark">§</span><span>grundlags<span>monitor</span></span></a><nav class="topnav" aria-label="Huvudnavigation"><a href="#now">På vänt</a><a href="#time">Tidslinje</a><a href="#archive">Arkiv</a><a href="#method">Metod</a></nav><div class="top-meta"><span class="live-dot"></span> Senast synkad ${formatShortDate(data.generatedAt)}</div></header>`;
}

function renderHero() {
  const election = data.election?.nextDate;
  const remaining = daysUntil(election);
  return `<section class="hero" id="top"><div class="hero-copy"><div class="eyebrow warm">Sveriges konstitutionella minne · 01</div><h1>Grundlagen ändras<br><em>inte i det tysta.</em></h1><p class="hero-intro">En öppen tidsmaskin för de fyra grundlagarna. Följ beslutet som vilar, se vad som redan trätt i kraft och läs källorna som binder ihop varje steg.</p><div class="hero-actions"><a class="button button-light" href="#time">Dra i tidslinjen <span>↓</span></a><a class="text-action" href="#method">Så läser du datan <span>↗</span></a></div></div><div class="hero-visual" aria-label="Översikt av datan"><div class="orbit orbit-one"></div><div class="orbit orbit-two"></div><div class="hero-card hero-card-main"><span class="card-kicker">Valet som skiljer besluten åt</span><strong>${formatDate(election)}</strong><span class="countdown">${remaining !== null && remaining >= 0 ? `${remaining} dagar kvar` : 'valet passerat'}</span></div><div class="hero-card hero-card-side"><span class="card-kicker">Vilande nu</span><strong>${data.pending.length}</strong><span>förslag efter första beslutet</span></div><div class="hero-stamp">RF<br>TF<br>YGL<br>SO</div></div></section>`;
}

function renderStats() {
  const dated = data.changes.filter((item) => item.date).length;
  const fetched = Object.values(versionReport.laws).reduce((sum, law) => sum + law.fetchedVersions, 0);
  return `<section class="stats-shell" aria-label="Nyckeltal"><article class="stat-card stat-accent"><span class="stat-label">På vänt efter första beslut</span><strong>${data.pending.length}</strong><span class="stat-note">kräver ny riksdag</span></article><article class="stat-card"><span class="stat-label">Bekräftade SFS-händelser</span><strong>${data.changes.length}</strong><span class="stat-note">${dated} med ikraftdatum</span></article><article class="stat-card"><span class="stat-label">Uttryckligen förkastad</span><strong>${data.aborted.length}</strong><span class="stat-note">historiskt kontrollfall</span></article><article class="stat-card stat-yellow"><span class="stat-label">Ferenda-versioner</span><strong>${fetched}</strong><span class="stat-note">fulltext hämtad</span></article></section>`;
}

function renderMilestone(item) {
  const election = item.interveningElection?.date || item.nextElection || data.election?.nextDate;
  const remaining = daysUntil(election);
  return `<div class="milestone-rail"><div class="milestone done"><span class="milestone-dot"></span><div><small>Första beslutet</small><strong>${formatShortDate(item.firstDecisionDate)}</strong><span>${escapeHTML(item.riksdag?.beteckning || 'Riksdagen')} · vilande</span></div></div><div class="milestone next"><span class="milestone-dot"></span><div><small>Val mellan besluten</small><strong>${formatShortDate(election)}</strong><span class="accent-text">${remaining !== null && remaining >= 0 ? `${remaining} dagar kvar` : 'Valet passerat'}</span></div></div><div class="milestone future"><span class="milestone-dot"></span><div><small>Andra beslutet</small><strong>Efter valet</strong><span>ny riksdag måste säga samma sak</span></div></div></div>`;
}

function renderPendingCard(item) {
  const affected = [item.constitutionId, ...(item.alsoConstitutionIds || [])].map((id) => lawById[id]).filter(Boolean);
  const tone = palette[item.constitutionId] || 'neutral';
  return `<article class="pending-card"><div class="pending-body"><div class="case-topline">${statusBadge('VILANDE', 'pending')}<span class="law-stack">${affected.map((law) => `<i class="law-pill law-${palette[law.id] || 'slate'}">${escapeHTML(law.short)}</i>`).join('')}</span><span class="case-id">${escapeHTML(item.riksdag?.riksmote || '')} / ${escapeHTML(item.riksdag?.beteckning || '')}</span></div><h3>${escapeHTML(item.title)}</h3><p>${escapeHTML(item.summary)}</p><div class="case-footer"><span class="source-label">Underlag</span>${sourceLinks(item.sources || [])}${link(item.riksdagUrl, 'Riksdagens ärende', 'source-link')}</div></div><div class="pending-side ${tone}">${renderMilestone(item)}${item.riksdag?.vote ? `<div class="vote-line"><span>Första votering</span><b>${escapeHTML(item.riksdag.vote.yes)} ja</b><span>·</span><b>${escapeHTML(item.riksdag.vote.no)} nej</b></div>` : ''}</div></article>`;
}

function renderNow() {
  return `<section class="section section-now" id="now"><div class="section-heading"><div><div class="eyebrow warm">02 / Nu</div><h2>Det som väntar<br><em>på väljarna.</em></h2></div><p>Ett grundlagsförslag behöver två likalydande beslut med ett riksdagsval emellan. Här syns de sju ärenden som Riksdagen har antagit som vilande inför 2026 års val.</p></div><div class="pending-list">${data.pending.map(renderPendingCard).join('')}</div><div class="queue-note"><span class="note-mark">i</span><p><strong>Efter valet</strong> kan den nyvalda riksdagen fatta det andra beslutet. Det måste ha samma innehåll som det första. Ett saknat beslut klassas inte som förkastat utan ligger kvar som en granskningsfråga.</p></div></section>`;
}

function timelineMarkers(law) {
  return datedChanges.filter((item) => item.constitutionId === law.id).map((item) => {
    const left = Math.max(0, Math.min(100, ((eventYear(item) - minYear) / (maxYear - minYear)) * 100));
    const selected = state.selected === item.id ? ' is-selected' : '';
    return `<button class="timeline-marker${selected}" style="left:${left}%" data-select="${escapeHTML(item.id)}" title="${escapeHTML(item.sfs)} · ${escapeHTML(String(eventYear(item)))}"><span></span><b>${escapeHTML(String(eventYear(item)))}</b></button>`;
  }).join('');
}

function renderTimeline() {
  const years = [minYear, 1974, 1991, 2003, 2011, 2019, 2023, maxYear].filter((year, index, arr) => year >= minYear && year <= maxYear && arr.indexOf(year) === index).sort((a, b) => a - b);
  const visible = datedChanges.filter((item) => eventYear(item) <= state.year).sort((a, b) => (b.date || '').localeCompare(a.date || '') || b.sfs.localeCompare(a.sfs));
  const selected = data.changes.find((item) => item.id === state.selected) || visible[0];
  return `<section class="section timeline-section" id="time"><div class="section-heading timeline-heading"><div><div class="eyebrow warm">03 / Tid</div><h2>Flytta dig genom<br><em>grundlagsminnet.</em></h2></div><div class="timeline-caption"><strong>${state.year}</strong><span>${visible.length} registrerade händelser fram till året</span></div></div><div class="time-machine"><div class="slider-row"><span>${minYear}</span><input id="year-slider" type="range" min="${minYear}" max="${maxYear}" value="${state.year}" step="1" aria-label="Välj årtal"/><span>${maxYear}</span></div><div class="year-readout"><span>Du tittar på</span><strong>${state.year}</strong><span class="readout-rule"></span><span>${state.year === maxYear ? 'senaste synkade läge' : 'historiskt läge'}</span></div><div class="timeline-lanes">${laws.map((law) => `<div class="timeline-lane"><div class="lane-label"><i class="law-pill law-${palette[law.id]}">${escapeHTML(law.short)}</i><span>${escapeHTML(law.title)}</span></div><div class="lane-track"><div class="track-line"></div>${timelineMarkers(law)}</div></div>`).join('')}</div><div class="timeline-years">${years.map((year) => `<span style="left:${((year - minYear) / (maxYear - minYear)) * 100}%">${year}</span>`).join('')}</div></div><div class="timeline-detail-grid"><div class="event-stream"><div class="subheading"><span>Händelser i det valda läget</span><span>${visible.length} / ${datedChanges.length}</span></div>${visible.slice(0, 9).map(renderEventRow).join('') || '<p class="empty-state">Inga daterade ändringar i detta läge.</p>'}</div>${selected ? renderSelectedEvent(selected) : '<div class="selected-event empty-state">Välj en punkt i tidslinjen.</div>'}</div></section>`;
}

function renderEventRow(item) {
  const law = lawById[item.constitutionId] || {};
  const selected = state.selected === item.id ? ' event-selected' : '';
  return `<button class="event-row${selected}" data-select="${escapeHTML(item.id)}"><span class="event-year">${escapeHTML(String(eventYear(item) || '—'))}</span><span class="event-law law-${palette[item.constitutionId] || 'slate'}">${escapeHTML(law.short || '—')}</span><span class="event-main"><b>${escapeHTML(item.title)}</b><small>${escapeHTML(item.sfs)} · ikraft ${formatShortDate(item.date)}</small></span><span class="event-arrow">↗</span></button>`;
}

function renderSelectedEvent(item) {
  const law = lawById[item.constitutionId] || {};
  const patch = patchByKey[`${item.constitutionId}:${item.sfs}`];
  const replaces = (item.metadata?.ersatter || []).map((url) => String(url).split('#').pop()).filter(Boolean);
  const inserts = (item.metadata?.inforsI || []).map((url) => String(url).split('#').pop()).filter(Boolean);
  return `<aside class="selected-event"><div class="selected-top"><span class="eyebrow">Vald händelse</span>${statusBadge('BEKRÄFTAD', 'confirmed')}</div><i class="selected-law law-pill law-${palette[item.constitutionId] || 'slate'}">${escapeHTML(law.short || '—')}</i><h3>${escapeHTML(item.sfs)}</h3><p>${escapeHTML(item.description || item.title)}</p><dl class="metadata-list"><div><dt>Ikraft</dt><dd>${formatDate(item.date)}</dd></div><div><dt>Förarbeten</dt><dd>${escapeHTML((item.preparatoryWorks || []).slice(0, 3).join(' · ') || 'saknas')}</dd></div>${replaces.length ? `<div><dt>Ersätter</dt><dd>${escapeHTML(replaces.join(' · '))}</dd></div>` : ''}${inserts.length ? `<div><dt>Förs in i</dt><dd>${escapeHTML(inserts.join(' · '))}</dd></div>` : ''}</dl><div class="selected-actions">${link(item.versionUrl, 'Öppna Ferenda-version', 'button button-dark')}${patch ? link(patch.path, `Git-patch · ${patch.changedLines} rader`, 'button button-outline') : '<span class="patch-unavailable">Ingen separat textpatch i Ferendas versionskatalog</span>'}</div></aside>`;
}

function filteredArchive() {
  const query = state.query.trim().toLowerCase();
  return data.changes.filter((item) => {
    const lawMatch = state.law === 'all' || item.constitutionId === state.law;
    const yearMatch = !item.date || eventYear(item) <= state.year;
    const haystack = [item.sfs, item.title, item.description, ...(item.preparatoryWorks || [])].join(' ').toLowerCase();
    return lawMatch && yearMatch && (!query || haystack.includes(query));
  });
}

function renderArchive() {
  const items = filteredArchive();
  return `<section class="section archive-section" id="archive"><div class="section-heading"><div><div class="eyebrow warm">04 / Då</div><h2>Ändrings-<br><em>registret.</em></h2></div><p>Ferendas register över SFS och konsolideringar. Sök i metadata, följ hänvisningarna och öppna den textversion som faktiskt finns exponerad.</p></div><div class="archive-toolbar"><div class="law-tabs"><button class="${state.law === 'all' ? 'active' : ''}" data-law="all">Alla <b>${data.changes.length}</b></button>${laws.map((law) => `<button class="${state.law === law.id ? 'active' : ''}" data-law="${law.id}">${escapeHTML(law.short)} <b>${data.changes.filter((item) => item.constitutionId === law.id).length}</b></button>`).join('')}</div><label class="search-box"><span>⌕</span><input id="archive-search" type="search" value="${escapeHTML(state.query)}" placeholder="Sök SFS, paragraf eller förarbete"/></label></div><div class="archive-header"><span>År</span><span>Lag</span><span>Ändring</span><span>Ikraft</span><span>Status</span></div><div class="archive-list">${items.slice(0, 80).map(renderArchiveRow).join('') || '<p class="empty-state">Inga träffar. Prova ett annat sökord.</p>'}</div><div class="archive-footer"><span>Visar ${Math.min(items.length, 80)} av ${items.length} träffar i valt läge</span><span>Poster utan ikraftdatum visas med metadata men placeras inte på tidslinjen.</span></div></section>`;
}

function renderArchiveRow(item) {
  const law = lawById[item.constitutionId] || {};
  const patch = patchByKey[`${item.constitutionId}:${item.sfs}`];
  return `<button class="archive-row" data-select="${escapeHTML(item.id)}"><span class="archive-year">${escapeHTML(String(eventYear(item) || '—'))}</span><span class="archive-law"><i class="law-pill law-${palette[item.constitutionId] || 'slate'}">${escapeHTML(law.short || '—')}</i><small>${escapeHTML(law.title || '')}</small></span><span class="archive-change"><b>${escapeHTML(item.sfs)}</b><strong>${escapeHTML(item.title)}</strong><small>${escapeHTML(item.description || '')}</small></span><span class="archive-date">${formatShortDate(item.date)}${patch ? '<small class="patch-flag">+ patch</small>' : ''}</span>${statusBadge('Bekräftad', 'confirmed')}</button>`;
}

function renderEvidence() {
  return `<section class="section evidence-section" id="evidence"><div class="section-heading"><div><div class="eyebrow warm">05 / Kontroll</div><h2>Bekräftad,<br>förkastad,<br><em>eller okänd?</em></h2></div><p>Tre olika saker kräver tre olika färger. Ett uttryckligen förkastat förslag kan beläggas. En gammal sökträff utan slutligt SFS-matchning kan bara visas som signal.</p></div><div class="evidence-grid"><div class="aborted-card">${data.aborted.map((item) => `<div class="evidence-item">${statusBadge('FÖRKASTAD', 'aborted')}<div class="evidence-item-head"><span>${formatShortDate(item.finalDecisionDate)}</span><span>${escapeHTML(item.vote?.yes)} ja / ${escapeHTML(item.vote?.no)} nej</span></div><h3>${escapeHTML(item.title)}</h3><p>${escapeHTML(item.summary)}</p><div class="vote-strip"><span>Slutlig votering</span><strong>${escapeHTML(item.vote?.yes)} ja</strong><strong>${escapeHTML(item.vote?.no)} nej</strong><span>${escapeHTML(item.vote?.abstain)} avstod</span></div>${link(item.sourceUrl, 'Läs protokollet', 'source-link')}</div>`).join('')}</div><div class="signals-card"><div class="signals-head"><span class="eyebrow">Ferenda-sökning</span><strong>${data.signals.length}</strong></div><p>Historiska träffar som nämner vilande grundlagsändringar. De är inte automatiskt fallna.</p><div class="signal-list">${data.signals.slice(0, 9).map((signal) => `<a href="${escapeHTML(signal.url)}" target="_blank" rel="noreferrer"><span>${escapeHTML(signal.identifier || signal.kind || 'signal')}</span><b>${escapeHTML(signal.title || '')}</b><i class="${signal.resolution === 'matched-to-confirmed-amendment' ? 'signal-match' : ''}">${signal.resolution === 'matched-to-confirmed-amendment' ? 'matchad' : 'granska'} ↗</i></a>`).join('')}</div><small class="signals-note">Visar 9 av ${data.signals.length}. ”Granska” är en öppen fråga, inte ett påstående om avbrott.</small></div></div></section>`;
}

function renderMethod() {
  const benchmarkRate = benchmark.metrics?.evidenceRecall?.rate ?? 0;
  const fetched = Object.values(versionReport.laws).reduce((sum, law) => sum + law.fetchedVersions, 0);
  const catalog = Object.values(versionReport.laws).reduce((sum, law) => sum + law.catalogVersions, 0);
  const matched = benchmark.metrics?.evidenceRecall?.matched ?? 0;
  const expected = benchmark.metrics?.evidenceRecall?.expected ?? 0;
  return `<section class="section method-section" id="method"><div class="method-intro"><div class="eyebrow warm">06 / Metod</div><h2>Spårbart hela vägen<br><em>till källan.</em></h2><p>Snapshoten byggs utan PDF-parsing. SFS-metadata ger identitet, ikraftträdande och hänvisningar; Riksdagens öppna data ger ärendets beslut och status.</p></div><div class="method-cards"><article><span>01</span><h3>Ferenda / lagen.nu</h3><p>Dokument, amendments, SFS-metadata och exponerade konsolideringar för de fyra grundlagarna.</p><a href="${escapeHTML(data.sources.ferendaOpenApi)}" target="_blank" rel="noreferrer">API-dokumentation ↗</a></article><article><span>02</span><h3>Riksdagen</h3><p>KU-betänkanden, beslut, voteringar och dokumentlista används för att hitta vilande första beslut.</p><a href="${escapeHTML(data.sources.riksdagOpenData)}" target="_blank" rel="noreferrer">Öppna data ↗</a></article><article><span>03</span><h3>Regressionskontroll</h3><p>${matched} av ${expected} statiska bevisenheter matchar i senaste körningen.</p><strong class="method-score">${(benchmarkRate * 100).toFixed(0)}%</strong></article></div><div class="method-metrics"><div><span>Versionsexperiment</span><strong>${fetched}/${catalog}</strong><small>Ferenda-sidor hämtade</small></div><div><span>Tidslinje</span><strong>${datedChanges.length}</strong><small>poster med datum</small></div><div><span>Öppen fråga</span><strong>${data.changes.length - datedChanges.length}</strong><small>SFS-poster utan ikraftdatum</small></div><div><span>Begränsning</span><strong>SO</strong><small>saknar versioner i API:t</small></div></div><p class="method-disclaimer">Se <a href="/VERSIONING_REPORT.md">VERSIONING_REPORT.md</a> och <a href="/DATA_BENCHMARK.md">DATA_BENCHMARK.md</a> för körningsresultat. En textpatch jämför normaliserad HTML och är inte en juridiskt auktoritativ redline.</p></section><footer class="footer"><span>GRUNDLAGSMONITOR / ÖPPEN PROTOTYP</span><span>Data synkad ${formatShortDate(data.generatedAt)} · ${data.changes.length} SFS-händelser</span></footer>`;
}

function render() {
  app.innerHTML = `${renderTopbar()}<main>${renderHero()}${renderStats()}${renderNow()}${renderTimeline()}${renderArchive()}${renderEvidence()}${renderMethod()}</main>`;
  bindEvents();
}

function bindEvents() {
  document.querySelectorAll('[data-select]').forEach((element) => element.addEventListener('click', () => {
    state.selected = element.dataset.select;
    render();
    document.querySelector('.selected-event')?.scrollIntoView({ behavior: 'smooth', block: 'center' });
  }));
  document.querySelectorAll('[data-law]').forEach((element) => element.addEventListener('click', () => {
    state.law = element.dataset.law;
    render();
    document.querySelector('#archive')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }));
  document.querySelector('#year-slider')?.addEventListener('input', (event) => {
    state.year = Number(event.target.value);
    render();
    document.querySelector('#time')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  });
  document.querySelector('#archive-search')?.addEventListener('input', (event) => {
    state.query = event.target.value;
    const archive = document.querySelector('#archive');
    const replacement = document.createElement('div');
    replacement.innerHTML = renderArchive();
    archive.replaceWith(replacement.firstElementChild);
    bindEvents();
    document.querySelector('#archive-search')?.focus();
  });
}

render();
