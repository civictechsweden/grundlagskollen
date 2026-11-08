import data from 'virtual:grundlagskollen-data';
import './style.css';

const app = document.querySelector('#app');
const lawById = Object.fromEntries(data.constitutions.map((law) => [law.id, law]));
const sfsById = Object.fromEntries(data.changes.map((change) => [change.sfs, change]));
const elections = [...(data.election?.dates || [])].sort((a, b) => a.date.localeCompare(b.date));
const checkedAt = data.currentRefreshedAt || data.generatedAt;
const recentSince = new Date(checkedAt);
recentSince.setUTCFullYear(recentSince.getUTCFullYear() - 1);
const records = data.proposals.filter((proposal) => proposal.firstDecision?.date)
  .sort((a, b) => b.firstDecision.date.localeCompare(a.firstDecision.date) || a.title.localeCompare(b.title, 'sv'));
const currentRecords = records.filter((record) => record.status === 'pending' ||
  (record.parliamentaryProgress && record.finalDecision?.date >= recentSince.toISOString().slice(0, 10)));
const pending = currentRecords.filter((record) => record.status === 'pending');
const decided = currentRecords.filter((record) => record.finalDecision?.date)
  .sort((a, b) => b.finalDecision.date.localeCompare(a.finalDecision.date));
const minYear = Math.min(1867, ...records.map((record) => yearOf(record.firstDecision.date)));
const maxYear = Math.max(new Date().getFullYear(), ...records.map((record) => yearOf(record.firstDecision.date)));
const params = new URLSearchParams(location.search);
const state = { query: params.get('q') || '', law: params.get('law') || 'all', status: params.get('status') || 'verified', year: maxYear };
if (!['all', ...Object.keys(lawById)].includes(state.law)) state.law = 'all';
if (!['verified', 'all', 'pending', 'adopted', 'rejected', 'unresolved'].includes(state.status)) state.status = 'verified';
const chevron = '<svg class="chevron" viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true"><path d="m6 9 6 6 6-6"/></svg>';
const linkIcon = '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/></svg>';
const playIcon = '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="9"/><path d="m10 8 6 4-6 4z"/></svg>';
let copyFeedbackTimer;

function escapeHTML(value = '') {
  return String(value).replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;').replaceAll('"', '&quot;').replaceAll("'", '&#039;');
}

function renderSourceText(source) {
  if (!source.html) {
    return source.text.split(/\n\s*\n/).map((paragraph) => `<p>${escapeHTML(paragraph).replaceAll('\n', '<br>')}</p>`).join('');
  }
  const parsed = new DOMParser().parseFromString(source.html, 'text/html');
  const allowed = new Set(['p', 'ul', 'ol', 'li', 'strong', 'em', 'b', 'i', 'br', 'a', 'sub', 'sup']);
  const excluded = new Set(['script', 'style', 'iframe', 'object', 'embed', 'template', 'svg', 'math']);
  const renderNode = (node) => {
    if (node.nodeType === Node.TEXT_NODE) return escapeHTML(node.textContent);
    if (node.nodeType !== Node.ELEMENT_NODE || excluded.has(node.localName)) return '';
    const children = [...node.childNodes].map(renderNode).join('');
    const tag = node.localName;
    if (!allowed.has(tag)) return children;
    if (tag === 'br') return '<br>';
    let attributes = '';
    if (tag === 'a') {
      if (!node.hasAttribute('href')) return children;
      try {
        const url = new URL(node.getAttribute('href'), source.sourceUrl);
        if (!['http:', 'https:'].includes(url.protocol)) return children;
        attributes = ` href="${escapeHTML(url.href)}"`;
      } catch { return children; }
    }
    const ordinal = node.getAttribute(tag === 'ol' ? 'start' : 'value');
    if (['ol', 'li'].includes(tag) && /^-?\d+$/.test(ordinal || '')) {
      attributes = ` ${tag === 'ol' ? 'start' : 'value'}="${ordinal}"`;
    }
    return `<${tag}${attributes}>${children}</${tag}>`;
  };
  return [...parsed.body.childNodes].map(renderNode).join('');
}

function formatDate(value, long = false) {
  if (!value) return 'Datum saknas';
  const date = new Date(`${String(value).slice(0, 10)}T12:00:00`);
  return Number.isNaN(date.valueOf()) ? value : new Intl.DateTimeFormat('sv-SE', {
    day: 'numeric', month: long ? 'long' : 'short', year: 'numeric',
  }).format(date);
}

function yearOf(value) { return Number(String(value).slice(0, 4)); }
function safeId(value) { return String(value).replace(/[^a-zA-Z0-9_-]/g, '-'); }
function statusLabel(status) {
  return { adopted: 'Slutligt antagen', rejected: 'Förkastad', pending: 'Inväntar kammaren', unresolved: 'Utgång oklar' }[status] || 'Utgång oklar';
}
function lawNames(record) { return record.constitutionIds.map((id) => lawById[id]?.title || id.toUpperCase()).join(' · '); }
function sourceLink(document, label) {
  return document?.documentUrl ? `<a href="${escapeHTML(document.documentUrl)}">${escapeHTML(label)}</a>` : '';
}
function riksdagSection(document, section) {
  if (!document || !/^[a-z0-9]{2}01ku\d+$/i.test(document.documentId || '')) return document;
  // Riksdagen resolves this document-ID route to its canonical page, so
  // links do not depend on generating or maintaining Swedish title slugs.
  const id = document.documentId.toLowerCase();
  return {
    ...document,
    documentUrl: `https://www.riksdagen.se/sv/dokument-och-lagar/dokument/betankande/_${id}/#${section}`,
    ...(section === 'debatt' ? { webcastUrl: `https://www.riksdagen.se/sv/webb-tv/video/debatt-om-forslag/_${id}/` } : {}),
  };
}
function electionBetween(record) {
  return elections.find((election) => election.date > record.firstDecision.date && (!record.finalDecision?.date || election.date < record.finalDecision.date));
}
function electionLabel(election) {
  if (!election) return 'Inte identifierat i underlaget';
  if (election.precision === 9) return election.date.slice(0, 4);
  if (election.precision === 10) return new Intl.DateTimeFormat('sv-SE', { month: 'long', year: 'numeric' }).format(new Date(`${election.date}T12:00:00`));
  return formatDate(election.date);
}
function eventDate(event) {
  if (!event) return 'Inte identifierat i underlaget';
  return `${event.status === 'planned' ? 'Planerat ' : event.status === 'unconfirmed' ? 'Ej bekräftat · ' : ''}${formatDate(event.date)}`;
}
function timelineItem(label, value, kind = 'completed', document = null, showPlay = false) {
  return `<li class="milestone is-${kind}"><span class="milestone-dot" aria-hidden="true"></span><div><strong class="milestone-heading">${sourceLink(document, label) || escapeHTML(label)}${showPlay && kind === 'completed' && document?.documentUrl ? `<a class="debate-play" href="${escapeHTML(document.webcastUrl || document.documentUrl)}" aria-label="Se debatten på riksdagens webb-tv" title="Se debatten på riksdagens webb-tv">${playIcon}</a>` : ''}</strong><span>${escapeHTML(value)}</span></div></li>`;
}

function renderSfsTimeline(record) {
  if (record.status !== 'adopted' || !record.finalDecision) return '';
  const amendments = (record.sfsIds || []).map((id) => sfsById[id]).filter(Boolean);
  if (!amendments.length) return '';
  return `<li class="milestone is-completed"><span class="milestone-dot" aria-hidden="true"></span><div>
    <strong>${amendments.length > 1 ? 'Författningsändringar' : 'Författningsändring'}</strong>
    ${amendments.map((amendment) => `<span class="sfs-entry">SFS ${escapeHTML(amendment.sfs)}${amendments.length > 1 ? ` · ${escapeHTML(lawById[amendment.constitutionId]?.title || '')}` : ''}${amendment.effectiveDate ? `<span class="sfs-effective">Gäller från <time datetime="${escapeHTML(amendment.effectiveDate)}">${escapeHTML(formatDate(amendment.effectiveDate))}</time></span>` : ''}${amendment.printedVersionUrl || amendment.comparisonUrl ? `<span class="sfs-links">${amendment.printedVersionUrl ? `<a href="${escapeHTML(amendment.printedVersionUrl)}" aria-label="Tryckt version av SFS ${escapeHTML(amendment.sfs)}">Tryckt version</a>` : ''}${amendment.comparisonUrl ? `<a href="${escapeHTML(amendment.comparisonUrl)}" aria-label="SFS ${escapeHTML(amendment.sfs)} på lagen.nu">lagen.nu</a>` : ''}</span>` : ''}</span>`).join('')}
  </div></li>`;
}

function renderTimeline(record) {
  const firstProgress = record.firstDecision.parliamentaryProgress;
  const progress = record.parliamentaryProgress;
  const election = electionBetween(record);
  const electionComplete = election && election.date <= String(checkedAt).slice(0, 10);
  return `<ol class="decision-timeline" aria-label="Ärendets steg">
    ${firstProgress?.committee ? timelineItem('Utskottets förslag', eventDate(firstProgress.committee), firstProgress.committee.status, riksdagSection(record.firstDecision, 'beredning')) : ''}
    ${firstProgress?.debate ? timelineItem('Debatt i kammaren', eventDate(firstProgress.debate), firstProgress.debate.status, riksdagSection(record.firstDecision, 'debatt'), true) : ''}
    ${timelineItem('Första beslutet i kammaren', formatDate(record.firstDecision.date), 'completed', riksdagSection(record.firstDecision, 'beslut'))}
    ${timelineItem('Riksdagsval däremellan', electionLabel(election), electionComplete ? 'completed' : 'planned', election?.wikipediaUrl ? { documentUrl: election.wikipediaUrl } : null)}
    ${progress?.committee ? timelineItem('Utskottets förslag', eventDate(progress.committee), progress.committee.status, riksdagSection(progress, 'beredning')) : ''}
    ${progress?.debate ? timelineItem('Debatt i kammaren', eventDate(progress.debate), progress.debate.status, riksdagSection(progress, 'debatt'), true) : ''}
    ${timelineItem('Andra beslutet i kammaren', record.finalDecision?.date
      ? `${record.status === 'adopted' ? 'Antagen' : record.status === 'rejected' ? 'Förkastad' : 'Utgång oklar'} · ${formatDate(record.finalDecision.date)}`
      : record.nextDecision?.date ? `Planerat ${formatDate(record.nextDecision.date)}` : 'Inte identifierat i underlaget', record.finalDecision?.date ? 'completed' : 'planned', riksdagSection(record.finalDecision || record.nextDecision || progress, 'beslut'))}
    ${renderSfsTimeline(record)}
  </ol>`;
}

function renderCard(record, context = 'current') {
  const id = `${context === 'history' ? 'history' : 'case'}-${safeId(record.proposalId)}`;
  const finalDate = record.finalDecision?.date;
  return `<details class="change-card ${context === 'history' ? 'history-card' : ''}" id="${id}" data-card-year="${yearOf(record.firstDecision.date)}">
    <summary>
      ${context === 'history' ? `<time class="change-date" datetime="${escapeHTML(record.firstDecision.date)}">${escapeHTML(formatDate(record.firstDecision.date))}</time>` : ''}
      <div class="change-main">
        <h3>${escapeHTML(record.sourceText?.title || record.title)}</h3>
        <p class="change-laws">${escapeHTML(lawNames(record))}</p>
      </div>
      <div class="change-state"><span class="status is-${record.status}">${escapeHTML(statusLabel(record.status))}</span>
        ${context !== 'history' ? `<span class="state-date">${finalDate ? escapeHTML(formatDate(finalDate)) : record.nextDecision?.date ? `Planerat ${escapeHTML(formatDate(record.nextDecision.date))}` : 'Datum ännu inte identifierat'}</span>` : ''}
      </div>
      <span class="card-actions"><button class="permalink" type="button" data-copy-link="${id}" aria-label="Kopiera länk till ärendet: ${escapeHTML(record.sourceText?.title || record.title)}" title="Kopiera länk till ärendet">${linkIcon}</button>${chevron}</span>
    </summary>
    <div class="change-detail">
      <div class="detail-copy">
        <h4>${record.sourceText?.kind === 'decision_notice' ? 'Riksdagens beslut i korthet' : record.sourceText?.kind === 'committee_notice' ? 'Utskottets förslag' : 'Sammanfattning ur betänkandet'}</h4>
        ${record.sourceText ? `<p class="source-attribution">Källa: Riksdagens öppna data.</p><div class="source-text">${renderSourceText(record.sourceText)}</div>` : '<p>Ingen sammanfattning finns i det hämtade underlaget. Läs betänkandet hos riksdagen via länkarna i tidslinjen.</p>'}
        ${record.status === 'unresolved' ? '<p class="decision-note">Underlaget saknar ett säkert slutligt utfall. Det betyder inte att förslaget fortfarande är aktuellt eller att det har förkastats.</p>' : ''}
      </div>
      <div class="detail-progress"><h4>Från förslag till grundlag</h4>${renderTimeline(record)}${record.status !== 'adopted' && record.sfsIds?.length ? `<p class="timeline-references">SFS-referenser: ${record.sfsIds.map((sfs) => sfsById[sfs]?.lawUrl ? `<a href="${escapeHTML(sfsById[sfs].lawUrl)}">${escapeHTML(sfs)}</a>` : escapeHTML(sfs)).join(', ')}</p>` : ''}</div>
    </div>
  </details>`;
}

function renderShell() {
  const nextDates = pending.map((record) => record.nextDecision?.date).filter(Boolean).sort();
  app.innerHTML = `
    <a class="skip-link" href="#main">Hoppa till innehållet</a>
    <header class="site-header"><div class="header-inner">
      <a class="brand" href="#top"><span class="brand-mark" aria-hidden="true">§</span>Grundlagskollen</a>
      <nav aria-label="Huvudnavigation"><a href="#aktuellt">Aktuellt</a><a href="#historik">Historik</a><a href="#sa-fungerar-det">Så fungerar det</a></nav>
    </div></header>
    <main id="main"><div id="top"></div>
      <section class="intro" aria-labelledby="page-title">
        <h1 id="page-title">Vad händer med grundlagarna?</h1>
        <p>Följ ändringarna i Sveriges fyra grundlagar (och riksdagsordningen).</p><p>All information hämtas från Riksdagens <a href="${escapeHTML(data.sources.riksdagOpenData)}">öppna data</a>.</p>
        <p class="updated">Senast uppdaterad <time datetime="${escapeHTML(String(checkedAt).slice(0, 10))}">${escapeHTML(formatDate(checkedAt, true))}</time></p>
      </section>
      <section id="sa-fungerar-det" class="explanation" aria-labelledby="process-heading">
        <h2 id="process-heading">Två beslut. Ett val emellan.</h2>
        <p>En grundlag ändras genom två likalydande beslut av riksdagen, med ett riksdagsval mellan besluten.</p>
        <ol class="process-steps">
          <li><strong>Första beslutet</strong><p>Riksdagen antar förslaget som vilande.</p></li>
          <li><strong>Riksdagsval</strong><p>Väljarna väljer en ny riksdag.</p></li>
          <li><strong>Andra beslutet</strong><p>Riksdagen antar eller förkastar samma förslag.</p></li>
        </ol>
      </section>
      <section id="aktuellt" class="current-section" aria-labelledby="upcoming-heading">
        <div class="section-heading"><h2 id="upcoming-heading">På väg till andra beslutet</h2>${nextDates.length ? `<p class="next-date">Nästa planerade beslut: <strong>${escapeHTML(formatDate(nextDates[0], true))}</strong></p>` : ''}</div>
        <div class="changes-list current-list">${pending.length ? pending.map((record) => renderCard(record)).join('') : '<p class="empty-state">Inga förslag väntar på ett andra beslut i den aktuella bevakningen.</p>'}</div>
      </section>
      <section class="recent-section" aria-labelledby="recent-heading">
        <div class="section-heading"><h2 id="recent-heading">Senast avgjorda i kammaren</h2></div>
        <div class="changes-list">${decided.map((record) => renderCard(record)).join('') || '<p class="empty-state">Inga nya slutliga beslut i den aktuella bevakningen.</p>'}</div>
      </section>
      <section id="historik" class="history-section" aria-labelledby="history-heading">
        <div class="section-heading"><h2 id="history-heading">Utforska historiken</h2><p id="results-count" class="results-count" role="status" aria-live="polite"></p></div>
        <p class="section-intro">Ärendena är sorterade efter första beslutet, från nyast till äldst. Historiska fall med oklar utgång kan visas via statusfiltret.</p>
        <form class="filter-panel" role="search" aria-label="Sök bland grundlagsändringar">
          <div class="filter-row">
            <label class="search-filter" for="search-filter">Sök ärende<input type="search" id="search-filter" placeholder="Till exempel medborgarskap eller domstolar" value="${escapeHTML(state.query)}" /></label>
            <label for="law-filter">Grundlag<select id="law-filter"><option value="all">Alla grundlagar</option>${data.constitutions.map((law) => `<option value="${escapeHTML(law.id)}" ${state.law === law.id ? 'selected' : ''}>${escapeHTML(law.title)}</option>`).join('')}</select></label>
            <label for="status-filter">Status<select id="status-filter">
              <option value="verified">Kända utfall och aktuella</option><option value="all">Alla, även oklar utgång</option><option value="pending">Inväntar kammaren</option><option value="adopted">Slutligt antagen</option><option value="rejected">Förkastad</option><option value="unresolved">Utgång oklar</option>
            </select></label>
          </div>
          <div class="year-filter"><label for="year-filter">Hoppa till första beslutets år <output id="year-output" for="year-filter">${maxYear}</output></label><span class="range-end">${minYear}</span><input id="year-filter" type="range" min="${minYear}" max="${maxYear}" value="${maxYear}" aria-label="Hoppa till första beslutets år" /><span class="range-end">${maxYear}</span></div>
        </form>
        <div class="history-columns" aria-hidden="true"><span>Första beslutet</span><span>Ärende och berörda lagar</span><span>Status</span></div>
        <div id="changes-list" class="changes-list history-list"></div>
      </section>
      <footer id="kallor" class="site-footer"><div><strong>Öppen bevakning. Spårbara källor.</strong><p>Ärendetitlar, källtexter, beslutsuppgifter och planerade datum hämtas från <a href="${escapeHTML(data.sources.riksdagOpenData)}">Riksdagens öppna data</a>. Texterna är skrivna av Sveriges riksdag och återges utan omskrivning. Status och kopplingar mellan beslut beräknas automatiskt från underlaget.</p></div>
        <details class="method-note"><summary>Om underlaget och dess begränsningar ${chevron}</summary><p>Den aktuella bevakningen kontrollerades ${escapeHTML(formatDate(checkedAt, true))}. Historiska lagändringar och SFS-versioner bygger på ett separat underlag från ${escapeHTML(formatDate(data.historicalSnapshotAt || data.generatedAt, true))}, med metadata från Ferenda och lagen.nu.</p><p>Historiken omfattar inte alla ändringar med säkert fastställda utfall. När ett slutligt beslut saknas visas utgången som oklar. Avsaknad av ett SFS-nummer betyder inte att riksdagen har sagt nej.</p><p><a href="/DATA_BENCHMARK.md">Läs datakontrollen</a> · <a href="/VERSIONING_REPORT.md">Läs rapporten om lagversioner</a></p></details>
      </footer>
    </main><p id="copy-feedback" class="copy-feedback" role="status" aria-live="polite"></p>`;
  document.querySelector('#status-filter').value = state.status;
  document.querySelector('.filter-panel').addEventListener('submit', (event) => event.preventDefault());
  document.querySelector('#search-filter').addEventListener('input', (event) => { state.query = event.target.value; renderList(); updateURL(); });
  for (const name of ['law', 'status']) {
    document.querySelector(`#${name}-filter`).addEventListener('change', (event) => { state[name] = event.target.value; renderList(); updateURL(); });
  }
  document.querySelector('#year-filter').addEventListener('input', (event) => { state.year = Number(event.target.value); document.querySelector('#year-output').value = state.year; });
  document.querySelector('#year-filter').addEventListener('change', scrollListToYear);
  document.querySelector('#changes-list').addEventListener('click', (event) => {
    if (event.target.closest('[data-reset]')) {
      state.query = ''; state.law = 'all'; state.status = 'verified';
      document.querySelector('#search-filter').value = ''; document.querySelector('#law-filter').value = 'all'; document.querySelector('#status-filter').value = 'verified';
      renderList(); updateURL(); document.querySelector('#search-filter').focus();
    }
  });
}

function renderList() {
  const query = state.query.trim().toLocaleLowerCase('sv');
  const visible = records.filter((record) =>
    (state.law === 'all' || record.constitutionIds.includes(state.law)) &&
    (state.status === 'all' || (state.status === 'verified' ? record.status !== 'unresolved' : record.status === state.status)) &&
    (!query || [record.title, record.sourceText?.title, record.sourceText?.text, lawNames(record), record.firstDecision.documentId, record.finalDecision?.documentId, record.nextDecision?.documentId, ...(record.sfsIds || [])].join(' ').toLocaleLowerCase('sv').includes(query)));
  document.querySelector('#results-count').textContent = `${visible.length} av ${records.length} ärenden`;
  document.querySelector('#changes-list').innerHTML = visible.length ? visible.map((record) => renderCard(record, 'history')).join('') : '<div class="empty-state"><h3>Inga ärenden matchar sökningen</h3><p>Prova ett annat sökord eller välj fler statusar.</p><button type="button" data-reset>Återställ filtren</button></div>';
  document.querySelector('#year-filter').disabled = visible.length === 0;
}
function updateURL() {
  const search = new URLSearchParams();
  if (state.query) search.set('q', state.query);
  if (state.law !== 'all') search.set('law', state.law);
  if (state.status !== 'verified') search.set('status', state.status);
  history.replaceState(null, '', `${location.pathname}${search.size ? `?${search}` : ''}${location.hash}`);
}
function scrollListToYear() {
  const cards = [...document.querySelectorAll('.history-card')];
  const target = cards.find((card) => Number(card.dataset.cardYear) <= state.year) || cards.at(-1);
  target?.scrollIntoView({ behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth', block: 'start' });
}
function openLinkedRecord() {
  const id = location.hash.slice(1);
  const target = document.getElementById(id);
  if (target instanceof HTMLDetailsElement) {
    target.open = true;
    requestAnimationFrame(() => target.scrollIntoView({ block: 'start' }));
  }
}
app.addEventListener('click', async (event) => {
  const button = event.target.closest('[data-copy-link]');
  if (!button) return;
  event.preventDefault();
  event.stopPropagation();
  const url = new URL(location.href);
  url.hash = button.dataset.copyLink;
  const feedback = document.querySelector('#copy-feedback');
  clearTimeout(copyFeedbackTimer);
  try {
    await navigator.clipboard.writeText(url.href);
    feedback.classList.remove('is-error');
    feedback.textContent = 'Länk kopierad';
  } catch {
    feedback.classList.add('is-error');
    feedback.textContent = 'Länken kunde inte kopieras. Försök igen.';
  }
  copyFeedbackTimer = setTimeout(() => { feedback.textContent = ''; }, 3000);
});
window.addEventListener('hashchange', openLinkedRecord);
renderShell();
renderList();
openLinkedRecord();
