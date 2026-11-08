import data from 'virtual:grundlagsmonitor-data';
import './style.css';

const app = document.querySelector('#app');
const lawById = Object.fromEntries(data.constitutions.map((law) => [law.id, law]));
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

function escapeHTML(value = '') {
  return String(value).replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;').replaceAll('"', '&quot;').replaceAll("'", '&#039;');
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
function electionBetween(record) {
  return elections.find((election) => election.date > record.firstDecision.date && (!record.finalDecision?.date || election.date < record.finalDecision.date));
}
function electionLabel(election) {
  if (!election) return 'Inte identifierat i underlaget';
  if (election.precision === 9) return election.date.slice(0, 4);
  if (election.precision === 10) return new Intl.DateTimeFormat('sv-SE', { month: 'long', year: 'numeric' }).format(new Date(`${election.date}T12:00:00`));
  return formatDate(election.date);
}
function recommendationLabel(event) {
  if (event?.recommendation === 'adopt') return 'Föreslår ja';
  if (event?.recommendation === 'reject') return 'Föreslår nej';
  return 'Behandlat i utskottet';
}
function eventDate(event) {
  if (!event) return 'Inte identifierat i underlaget';
  return `${event.status === 'planned' ? 'Planerat ' : event.status === 'unconfirmed' ? 'Ej bekräftat · ' : ''}${formatDate(event.date)}`;
}
function timelineItem(label, value, kind = 'completed') {
  return `<li class="milestone is-${kind}"><span class="milestone-dot" aria-hidden="true"></span><div><strong>${escapeHTML(label)}</strong><span>${escapeHTML(value)}</span></div></li>`;
}

function renderTimeline(record) {
  const progress = record.parliamentaryProgress;
  const election = electionBetween(record);
  const electionComplete = election && election.date <= String(checkedAt).slice(0, 10);
  return `<ol class="decision-timeline" aria-label="Ärendets steg">
    ${timelineItem('Första beslutet i kammaren', formatDate(record.firstDecision.date))}
    ${timelineItem('Riksdagsval däremellan', electionLabel(election), electionComplete ? 'completed' : 'planned')}
    ${progress?.committee ? timelineItem('Utskottets behandling inför andra beslutet', `${progress.committee.status === 'completed' ? `${recommendationLabel(progress.committee)} · ` : ''}${eventDate(progress.committee)}`, progress.committee.status) : ''}
    ${progress?.debate ? timelineItem('Debatt i kammaren', eventDate(progress.debate), progress.debate.status) : ''}
    ${timelineItem('Andra beslutet i kammaren', record.finalDecision?.date
      ? `${record.status === 'adopted' ? 'Antagen' : record.status === 'rejected' ? 'Förkastad' : 'Utgång oklar'} · ${formatDate(record.finalDecision.date)}`
      : record.nextDecision?.date ? `Planerat ${formatDate(record.nextDecision.date)}` : 'Inte identifierat i underlaget', record.finalDecision?.date ? 'completed' : 'planned')}
  </ol>`;
}

function renderCard(record, context = 'current') {
  const id = `${context === 'history' ? 'history' : 'case'}-${safeId(record.proposalId)}`;
  const progress = record.parliamentaryProgress;
  const finalDate = record.finalDecision?.date;
  const committee = progress?.committee;
  return `<details class="change-card ${context === 'history' ? 'history-card' : ''}" id="${id}" data-card-year="${yearOf(record.firstDecision.date)}">
    <summary>
      ${context === 'history' ? `<time class="change-date" datetime="${escapeHTML(record.firstDecision.date)}">${escapeHTML(formatDate(record.firstDecision.date))}</time>` : ''}
      <div class="change-main">
        <h3>${escapeHTML(record.sourceText?.title || record.title)}</h3>
        <p class="change-laws">${escapeHTML(lawNames(record))}</p>
        ${context !== 'history' && committee?.status === 'completed' ? `<p class="committee-note">Utskottet: ${escapeHTML(recommendationLabel(committee).toLocaleLowerCase('sv'))} <span>· ${escapeHTML(formatDate(committee.date))}</span></p>` : ''}
      </div>
      <div class="change-state"><span class="status is-${record.status}">${escapeHTML(statusLabel(record.status))}</span>
        ${context !== 'history' ? `<span class="state-date">${finalDate ? escapeHTML(formatDate(finalDate)) : record.nextDecision?.date ? `Planerat ${escapeHTML(formatDate(record.nextDecision.date))}` : 'Datum ännu inte identifierat'}</span>` : ''}
      </div>
      ${chevron}
    </summary>
    <div class="change-detail">
      <div class="detail-copy">
        <h4>${record.sourceText?.kind === 'decision_notice' ? 'Riksdagens beslut i korthet' : record.sourceText?.kind === 'committee_notice' ? 'Riksdagens text om utskottets förslag' : 'Sammanfattning ur betänkandet'}</h4>
        ${record.sourceText ? `<p class="source-attribution">Text från Sveriges riksdag, återgiven utan omskrivning.</p><div class="source-text">${escapeHTML(record.sourceText.text)}</div>` : '<p>Ingen sammanfattning finns i det hämtade underlaget. Läs betänkandet hos riksdagen via källänkarna nedan.</p>'}
        ${record.sourceText?.title ? `<p class="official-title"><strong>Det första betänkandets titel</strong>${escapeHTML(record.title)}</p>` : ''}
        ${record.status === 'pending' ? `<p class="decision-note">${committee?.status === 'completed' ? 'Utskottets förslag är klart.' : 'Förslaget har antagits som vilande.'} Grundlagsändringen behöver fortfarande ett andra, likalydande beslut i kammaren.</p>` : ''}
        ${record.status === 'unresolved' ? '<p class="decision-note">Underlaget saknar ett säkert slutligt utfall. Det betyder inte att förslaget fortfarande är aktuellt eller att det har förkastats.</p>' : ''}
        <div class="source-links"><h4>Källor hos riksdagen</h4>
          ${sourceLink(record.firstDecision, 'Första beslutet')}
          ${progress ? sourceLink(progress, `${progress.designation} · utskott, debatt och kammarbeslut`) : sourceLink(record.finalDecision, 'Andra beslutet')}
          ${record.sourceText ? `<a href="${escapeHTML(record.sourceText.sourceUrl)}">Källan till texten ovan</a>` : ''}
          ${record.sfsIds?.length ? `<p>SFS: ${record.sfsIds.map((sfs) => `<a href="https://lagen.nu/${escapeHTML(sfs)}">${escapeHTML(sfs)}</a>`).join(', ')}</p>` : ''}
        </div>
        ${record.match?.method === 'explicit_first_decision_citation' ? `<div class="link-evidence"><h4>Kopplingen till första beslutet</h4><p>Det uppföljande betänkandet anger följande under ”Behandlade förslag”:</p><blockquote>${escapeHTML(record.match.evidence.evidence)}</blockquote><a href="${escapeHTML(record.match.evidence.sourceUrl)}">Läs hänvisningen i källtexten</a></div>` : record.finalDecision || record.nextDecision ? '<p class="decision-note">Kopplingen mellan betänkandena bygger på automatisk matchning av referenser. En uttrycklig hänvisning till det första beslutet har inte identifierats.</p>' : ''}
        <a class="permalink" href="#${id}">Länk till ärendet</a>
      </div>
      <div class="detail-progress"><h4>Från förslag till grundlag</h4>${renderTimeline(record)}</div>
    </div>
  </details>`;
}

function renderShell() {
  const nextDates = pending.map((record) => record.nextDecision?.date).filter(Boolean).sort();
  app.innerHTML = `
    <a class="skip-link" href="#main">Hoppa till innehållet</a>
    <header class="site-header"><div class="header-inner">
      <a class="brand" href="#top"><span class="brand-mark" aria-hidden="true">§</span>Grundlagsmonitor</a>
      <nav aria-label="Huvudnavigation"><a href="#aktuellt">Aktuellt</a><a href="#historik">Historik</a><a href="#sa-fungerar-det">Så fungerar det</a></nav>
    </div></header>
    <main id="main"><div id="top"></div>
      <section class="intro" aria-labelledby="page-title">
        <h1 id="page-title">Vad händer med grundlagarna?</h1>
        <p>Följ ändringarna i Sveriges fyra grundlagar. Se utskottens förslag, planerade beslut och riksdagens beslut direkt från öppna data.</p>
        <p class="updated">Riksdagsuppgifter kontrollerade <time datetime="${escapeHTML(String(checkedAt).slice(0, 10))}">${escapeHTML(formatDate(checkedAt, true))}</time></p>
      </section>
      <section id="aktuellt" class="current-section" aria-labelledby="upcoming-heading">
        <div class="section-heading"><h2 id="upcoming-heading">På väg till andra beslutet</h2>${nextDates.length ? `<p class="next-date">Nästa planerade beslut: <strong>${escapeHTML(formatDate(nextDates[0], true))}</strong></p>` : ''}</div>
        <p class="section-intro">Utskottet lämnar ett förslag. Kammaren fattar det slutliga beslutet. Öppna ett ärende för att följa stegen.</p>
        <div class="changes-list current-list">${pending.length ? pending.map((record) => renderCard(record)).join('') : '<p class="empty-state">Inga förslag väntar på ett andra beslut i den aktuella bevakningen.</p>'}</div>
      </section>
      <section class="recent-section" aria-labelledby="recent-heading">
        <div class="section-heading"><h2 id="recent-heading">Senast avgjorda i kammaren</h2></div>
        <p class="section-intro">Ett slutligt ja och ett ikraftträdande är olika steg. Läs riksdagens egen text om beslutet i varje ärende.</p>
        <div class="changes-list">${decided.map((record) => renderCard(record)).join('') || '<p class="empty-state">Inga nya slutliga beslut i den aktuella bevakningen.</p>'}</div>
      </section>
      <section id="sa-fungerar-det" class="explanation" aria-labelledby="process-heading">
        <h2 id="process-heading">Två beslut. Ett val emellan.</h2>
        <p>En grundlag ändras genom två likalydande beslut av riksdagen, med ett riksdagsval mellan besluten.</p>
        <ol class="process-steps">
          <li><strong>Första beslutet</strong><p>Riksdagen antar förslaget som vilande. Det är ännu ingen färdig grundlagsändring.</p></li>
          <li><strong>Riksdagsval</strong><p>Väljarna väljer en ny riksdag innan förslaget kan avgöras.</p></li>
          <li><strong>Andra beslutet</strong><p>Den nyvalda riksdagen antar eller förkastar samma förslag. Ett antaget förslag börjar gälla vid sitt ikraftträdande.</p></li>
        </ol>
        <details class="method-note"><summary>Vilken roll har utskottet? ${chevron}</summary><p>Konstitutionsutskottet bereder ärendet och lämnar ett förslag till kammaren. När betänkandet har justerats visar vi att utskottets behandling är klar. Det är ett annat steg än riksdagens beslut.</p><p>Utskott, debatt och beslut hämtas separat från Riksdagens öppna data. En planerad tid i ärendegången visas som planerad tills källan bekräftar att händelsen har inträffat. Datum kan ändras.</p><p>RO betyder riksdagsordningen. Den är inte en av de fyra grundlagarna, men vissa huvudbestämmelser kan beslutas i samma ordning.</p></details>
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
    </main>`;
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
window.addEventListener('hashchange', openLinkedRecord);
renderShell();
renderList();
openLinkedRecord();
