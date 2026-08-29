import data from '../../data/changes.json';
import './style.css';

const app = document.querySelector('#app');
const lawById = Object.fromEntries((data.constitutions || []).map((law) => [law.id, law]));
const lawOptions = (data.constitutions || []).filter((law) => law.sfs);

const elections = [
  '1976-09-19', '1979-09-16', '1982-09-19', '1985-09-15', '1988-09-18',
  '1991-09-15', '1994-09-18', '1998-09-20', '2002-09-15', '2006-09-17',
  '2010-09-19', '2014-09-14', '2018-09-09', '2022-09-11', '2026-09-13',
];

const proposalRecords = (data.proposals || [])
  .filter((proposal) => proposal.firstDecision?.date)
  .map((proposal) => ({
    id: proposal.proposalId,
    kind: 'proposal',
    title: proposal.title || 'Grundlagsändring',
    status: proposal.status,
    firstDate: proposal.firstDecision.date,
    year: yearOf(proposal.firstDecision.date),
    finalDate: proposal.finalDecision?.date || null,
    firstDocument: proposal.firstDecision,
    finalDocument: proposal.finalDecision,
    lawIds: proposal.constitutionIds || [],
    sfsIds: proposal.sfsIds || [],
  }));

const proposalSfsIds = new Set(proposalRecords.flatMap((record) => record.sfsIds));

const baselineRecords = lawOptions.map((law) => ({
  id: `${law.id}-${law.sfs}-original`,
  kind: 'baseline',
  title: `Ursprunglig lydelse av ${law.title}`,
  status: 'baseline',
  firstDate: null,
  year: yearOf(law.sfs),
  lawIds: [law.id],
  sfsIds: [law.sfs],
  lawUrl: law.uri,
  versionUrl: law.uri,
}));

const sfsRecords = (data.changes || [])
  .filter((change) => change.sfs && !proposalSfsIds.has(change.sfs))
  .map((change) => ({
    id: change.id,
    kind: 'sfs',
    title: change.title || 'Ändring registrerad i konsolideringen',
    status: 'confirmed',
    firstDate: change.date || null,
    year: yearOf(change.date || change.sfs),
    lawIds: [change.constitutionId],
    sfsIds: [change.sfs],
    lawUrl: change.lawUrl,
    versionUrl: change.versionUrl,
    preparatoryWorks: change.preparatoryWorks || [],
  }));

const records = [...baselineRecords, ...sfsRecords, ...proposalRecords]
  .filter((record) => record.year)
  .sort((a, b) => b.year - a.year || (b.firstDate || '').localeCompare(a.firstDate || '') || a.title.localeCompare(b.title, 'sv'));

const yearValues = records.map((record) => record.year).filter(Boolean);
const minYear = Math.min(...yearValues);
const maxYear = Math.max(new Date().getFullYear(), ...yearValues);
const state = { law: 'all', status: 'all', year: maxYear, open: null };

function escapeHTML(value = '') {
  return String(value)
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#039;');
}

function formatDate(value, fallback = 'Datum saknas') {
  if (!value) return fallback;
  const date = new Date(`${value}T12:00:00`);
  return Number.isNaN(date.valueOf())
    ? value
    : new Intl.DateTimeFormat('sv-SE', { day: 'numeric', month: 'short', year: 'numeric' }).format(date);
}

function formatRecordDate(record) {
  return record.firstDate ? formatDate(record.firstDate) : String(record.year);
}

function yearOf(value) {
  return Number(String(value || '').slice(0, 4));
}

function statusLabel(status) {
  if (status === 'adopted') return 'antagen';
  if (status === 'rejected') return 'förkastad';
  if (status === 'confirmed') return 'SFS-verifierad';
  if (status === 'baseline') return 'ursprunglig';
  return 'vilande';
}

function statusClass(status) {
  if (status === 'adopted') return 'is-adopted';
  if (status === 'rejected') return 'is-rejected';
  if (status === 'confirmed' || status === 'baseline') return 'is-confirmed';
  return 'is-pending';
}

function statusGroup(status) {
  if (status === 'adopted') return 'adopted';
  if (status === 'rejected') return 'rejected';
  if (status === 'confirmed' || status === 'baseline') return 'confirmed';
  return 'pending';
}

function lawLabel(id) {
  return lawById[id]?.short || id.toUpperCase();
}

function lawTitle(id) {
  return lawById[id]?.title || id.toUpperCase();
}

function safeId(value) {
  return String(value).replace(/[^a-zA-Z0-9_-]/g, '-');
}

function electionBetween(record) {
  if (record.kind !== 'proposal') return null;
  const candidates = elections.filter((date) => date > record.firstDate);
  if (record.finalDate) {
    return candidates.find((date) => date < record.finalDate) || null;
  }
  return candidates[0] || null;
}

function timelineEvent(label, date, missing = false) {
  return `<div class="timeline-event${missing ? ' is-missing' : ''}">
    <span class="timeline-dot" aria-hidden="true"></span>
    <span class="timeline-label">${escapeHTML(label)}</span>
    <time>${escapeHTML(date || 'Ej identifierat')}</time>
  </div>`;
}

function sourceLink(source, label) {
  const url = source?.documentUrl || source?.lawUrl || source?.url;
  if (!url) return '';
  return `<a href="${escapeHTML(url)}" target="_blank" rel="noreferrer">${escapeHTML(label)} ↗</a>`;
}

function matches(record) {
  const lawMatches = state.law === 'all' || record.lawIds.includes(state.law);
  const statusMatches = state.status === 'all' || statusGroup(record.status) === state.status;
  return lawMatches && statusMatches;
}

function filteredRecords() {
  return records.filter(matches);
}

function renderShell() {
  app.innerHTML = `
    <header class="site-header">
      <a class="brand" href="#top" aria-label="Grundlagsmonitor, gå till början">
        <span class="brand-mark" aria-hidden="true">§</span>
        <span>Grundlagsmonitor</span>
      </a>
    </header>
    <main id="top">
      <section class="filter-panel" aria-label="Filtrera och navigera bland grundlagsändringar">
        <div class="filter-row">
          <label class="law-filter" for="law-filter">
            <span>Grundlag</span>
            <select id="law-filter">
              <option value="all">Alla grundlagar</option>
              ${lawOptions.map((law) => `<option value="${escapeHTML(law.id)}">${escapeHTML(law.short)} · ${escapeHTML(law.title)}</option>`).join('')}
            </select>
          </label>
          <label class="status-filter" for="status-filter">
            <span>Status</span>
            <select id="status-filter">
              <option value="all">Alla statusar</option>
              <option value="pending">Vilande</option>
              <option value="adopted">Antagen</option>
              <option value="rejected">Förkastad</option>
              <option value="confirmed">SFS-historik</option>
            </select>
          </label>
          <div class="year-filter">
            <div class="year-filter-heading">
              <label for="year-filter">Tidslinje</label>
              <output id="year-output" for="year-filter">${maxYear}</output>
            </div>
            <input id="year-filter" type="range" min="${minYear}" max="${maxYear}" value="${maxYear}" step="1" aria-label="Scrolla listan till år" />
            <div class="range-ends" aria-hidden="true"><span>${minYear}</span><span>${maxYear}</span></div>
          </div>
        </div>
      </section>

      <section class="changes-section" aria-labelledby="changes-heading">
        <div class="list-heading">
          <h1 id="changes-heading">Grundlagarnas historik</h1>
          <p id="results-count" class="results-count"></p>
        </div>
        <div id="changes-list" class="changes-list"></div>
      </section>
    </main>
  `;

  document.querySelector('#law-filter').addEventListener('change', (event) => {
    state.law = event.target.value;
    state.open = null;
    renderList();
  });

  document.querySelector('#status-filter').addEventListener('change', (event) => {
    state.status = event.target.value;
    state.open = null;
    renderList();
  });

  document.querySelector('#year-filter').addEventListener('input', (event) => {
    state.year = Number(event.target.value);
    updateYearOutput();
    scrollListToYear();
  });
}

function renderCard(record) {
  const id = safeId(record.id);
  const isOpen = state.open === record.id;
  const laws = record.lawIds.map((lawId) => `<span title="${escapeHTML(lawTitle(lawId))}">${escapeHTML(lawLabel(lawId))}</span>`).join('');
  const sfs = record.sfsIds.length ? `<p class="detail-meta"><strong>SFS</strong> ${escapeHTML(record.sfsIds.join(' · '))}</p>` : '';

  return `<article class="change-card${isOpen ? ' is-open' : ''}" data-card-year="${record.year}">
    <button class="change-card-button" type="button" data-record-id="${escapeHTML(record.id)}" aria-expanded="${isOpen}" aria-controls="detail-${id}">
      <time class="change-date"${record.firstDate ? ` datetime="${escapeHTML(record.firstDate)}"` : ''}>${escapeHTML(formatRecordDate(record))}</time>
      <span class="change-main">
        <span class="change-title">${escapeHTML(record.title)}</span>
        <span class="change-laws">${laws || '<span>Grundlag saknas</span>'}</span>
      </span>
      <span class="status ${statusClass(record.status)}">${statusLabel(record.status)}</span>
      <span class="expand-mark" aria-hidden="true">${isOpen ? '−' : '+'}</span>
    </button>
    ${record.kind === 'proposal' ? renderProposalDetail(record, sfs) : renderSfsDetail(record, sfs)}
  </article>`;
}

function renderProposalDetail(record, sfs) {
  const election = electionBetween(record);
  return `<div id="detail-${safeId(record.id)}" class="change-detail" ${state.open === record.id ? '' : 'hidden'}>
    <div class="detail-topline">
      <span>Beslutsförlopp</span>
      <span>${escapeHTML(statusLabel(record.status))}</span>
    </div>
    <div class="decision-timeline" aria-label="Tidslinje för beslutet">
      ${timelineEvent('Första beslutet', formatDate(record.firstDate))}
      ${timelineEvent('Val däremellan', election ? formatDate(election) : null, !election)}
      ${timelineEvent('Andra beslutet', record.finalDate ? formatDate(record.finalDate) : null, !record.finalDate)}
    </div>
    <div class="detail-footer">
      <div>${sfs}<p class="detail-meta"><strong>Första beslut</strong> ${sourceLink(record.firstDocument, record.firstDocument?.documentId || 'Riksdagsdokument')}</p>${record.finalDocument ? `<p class="detail-meta"><strong>Andra beslut</strong> ${sourceLink(record.finalDocument, record.finalDocument.documentId || 'Riksdagsdokument')}</p>` : ''}</div>
      <span class="detail-note">${record.finalDate ? 'Slutligt beslut finns i underlaget.' : 'Slutligt beslut är inte identifierat i underlaget.'}</span>
    </div>
  </div>`;
}

function renderSfsDetail(record, sfs) {
  const isBaseline = record.kind === 'baseline';
  const version = record.versionUrl && record.versionUrl !== record.lawUrl
    ? `<p class="detail-meta"><strong>Lydelse</strong> <a href="${escapeHTML(record.versionUrl)}" target="_blank" rel="noreferrer">Visa konsoliderad lydelse ↗</a></p>`
    : '';
  const preparatoryWorks = record.preparatoryWorks?.length
    ? `<p class="detail-meta"><strong>Förarbeten</strong> ${escapeHTML(record.preparatoryWorks.join(' · '))}</p>`
    : '';
  const note = isBaseline
    ? 'Startpunkt i Ferendas SFS-historik för denna grundlag.'
    : record.firstDate
      ? 'Datumet är ikraftträdandet enligt Ferendas SFS-underlag.'
      : 'Ferendas SFS-underlag anger inget ikraftträdandedatum; året kommer från SFS-numret.';
  return `<div id="detail-${safeId(record.id)}" class="change-detail" ${state.open === record.id ? '' : 'hidden'}>
    <div class="detail-topline">
      <span>${isBaseline ? 'Ursprunglig lydelse' : 'SFS-historik'}</span>
      <span>${escapeHTML(statusLabel(record.status))}</span>
    </div>
    <div class="detail-footer detail-footer-sfs">
      <div>${sfs}<p class="detail-meta"><strong>Källa</strong> ${sourceLink(record, `SFS ${record.sfsIds[0]}`)}</p>${version}${preparatoryWorks}</div>
      <span class="detail-note">${escapeHTML(note)}</span>
    </div>
  </div>`;
}

function renderList() {
  const visible = filteredRecords();
  const list = document.querySelector('#changes-list');
  const count = document.querySelector('#results-count');
  const output = document.querySelector('#year-output');
  if (!list || !count || !output) return;

  updateYearOutput();
  count.textContent = `${visible.length} av ${records.length}`;
  list.innerHTML = visible.length
    ? visible.map(renderCard).join('')
    : '<p class="empty-state">Inga ändringar matchar filtren.</p>';

  list.querySelectorAll('[data-record-id]').forEach((button) => {
    button.addEventListener('click', () => {
      state.open = state.open === button.dataset.recordId ? null : button.dataset.recordId;
      renderList();
    });
  });
}

function updateYearOutput() {
  const output = document.querySelector('#year-output');
  if (!output) return;
  output.value = String(state.year);
  output.textContent = String(state.year);
}

function scrollListToYear() {
  const cards = [...document.querySelectorAll('.change-card')];
  if (!cards.length) return;
  const target = cards.reduce((best, card) => {
    const cardYear = Number(card.dataset.cardYear);
    const distance = cardYear <= state.year
      ? state.year - cardYear
      : 10000 + cardYear - state.year;
    if (!best || distance < best.distance) return { card, distance };
    return best;
  }, null)?.card;
  if (!target) return;

  const headerHeight = document.querySelector('.site-header')?.offsetHeight || 0;
  const filterHeight = document.querySelector('.filter-panel')?.offsetHeight || 0;
  const top = target.getBoundingClientRect().top + window.scrollY - headerHeight - filterHeight - 10;
  window.scrollTo({ top: Math.max(0, top), behavior: 'smooth' });
}

renderShell();
renderList();
