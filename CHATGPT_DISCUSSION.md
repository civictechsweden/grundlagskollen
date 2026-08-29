# Projekt: kartläggning och rekonstruktion av svenska grundlagsändringar

## 1. Syfte

Bygg ett reproducerbart dataset och ett skript/system som kartlägger svenska
grundlagsändringar, i första hand från 1975 till idag, med möjlighet att senare
gå bakåt till 1809 års regeringsform och äldre material.

Projektet har två huvudmål:

1. Identifiera samtliga förslag till grundlagsändringar som riksdagen antagit
   som vilande före ett val, och avgöra vad som hände med dem efter valet:
   - slutligt antagna,
   - förkastade,
   - eventuellt aldrig slutbehandlade,
   - eller oklara p.g.a. dataluckor.

2. Rekonstruera en maskinläsbar versionshistorik för Sveriges fyra grundlagar,
   där varje ändrings-SFS fungerar som en "patch", så att vi kan generera:
   - historiska konsoliderade versioner,
   - juridiska diffar,
   - textdiffar,
   - och länkar från varje ändring tillbaka till proposition, KU-betänkanden,
     riksdagsbeslut och riksdagsskrivelser.

De fyra nuvarande grundlagarna är:

- Regeringsformen (RF), SFS 1974:152
- Successionsordningen (SO), SFS 1810:0926
- Tryckfrihetsförordningen (TF), SFS 1949:105
- Yttrandefrihetsgrundlagen (YGL), SFS 1991:1469

# 2. Den konstitutionella processen

Huvudregeln finns idag i 8 kap. regeringsformen.

En grundlagsändring kräver i princip:

1. ett första riksdagsbeslut,
2. förslaget blir vilande,
3. ett riksdagsval hålls,
4. den nyvalda riksdagen samlas,
5. samma förslag måste antas en andra gång.

Det andra beslutet är alltså juridiskt nödvändigt och är inte bara en
administrativ bekräftelse.

Historiskt är principen mycket äldre än 1974 års RF.

KU:s historiska genomgång 2003/04:KU9 anger att ordningen med två beslut med
val emellan har hävd sedan 1766.

Under 1809 års RF fanns motsvarande konstruktion. 81 § RF krävde Konungens
och två riksdagars beslut, medan äldre riksdagsordning reglerade hur ett
grundlagsförslag skulle vila och sedan prövas på nytt.

KU 2003/04:KU9 är en viktig sekundär/officiell källa för hela denna historik.

# 3. Viktig terminologi: betänkande är inte samma sak som riksdagsbeslut

Var noggrann med datamodellen.

Ett KU-betänkande är utskottets förslag till hur riksdagen bör besluta.

Det faktiska beslutet fattas av kammaren.

Vi bör därför helst modellera åtminstone:

- proposition/förslag
- betänkande
- kammarbeslut
- protokoll
- riksdagsskrivelse

Betänkandet är dock ofta den bästa ingången i datan eftersom det beskriver
ärendet, lagförslaget och utskottets hemställan/förslag, medan Riksdagens
webbplats/statusdata även kan ange vad riksdagen faktiskt beslutade.

# 4. Primär datakälla: Riksdagens öppna data

Dokumentation:

<https://www.riksdagen.se/sv/dokument-och-lagar/riksdagens-oppna-data/>

Användarstöd:

<https://www.riksdagen.se/sv/dokument-och-lagar/riksdagens-oppna-data/anvandarstod/>

Dokument-ID:

<https://www.riksdagen.se/sv/dokument-och-lagar/riksdagens-oppna-data/anvandarstod/sa-fungerar-dokument-id/>

Riksdagens öppna data innehåller API, dataset och rådata.

Riksdagen uppger att det finns över 600 000 dokument/statusposter och material
så långt tillbaka som 1867, men dokumenttypernas täckning varierar över tid.

Dokument har stabila `dok_id`.

Exempel:

    GY01KU3

SFS är ett specialfall:

    sfs-1974-152

# 5. Identifiera första beslut: "antas som vilande"

Det verkar inte finnas ett perfekt metadatafält av typen:

    constitutional_decision_stage = first/vilande

Därför bör identifieringen använda en kombination av:

- dokumenttyp
- utskott
- datum/riksmöte
- dokumentrelationer
- standardiserade formuleringar i texten.

Primärt sökuttryck för modern data:

    "som vilande anta"

Andra former som bör fångas:

    "som vilande antagit"
    "vilande anta"
    "antagit som vilande"
    "antaga såsom vilande"
    "antaget att vila"
    "antaget till vilande"
    "vilande grundlagsförslag"
    "vilande grundlagsbeslut"
    "grundlagsenlig behandling"

Äldre material kräver äldre stavning:

    hvilande
    antaga
    grundlagsändringsförslag
    grundlagsenlig ordning

Sökningen bör kombineras med namn på grundlag:

    regeringsformen
    tryckfrihetsförordningen
    yttrandefrihetsgrundlagen
    successionsordningen

För modern period bör KU-betänkanden vara en mycket stark avgränsning.

# 6. Identifiera andra/slutliga beslut

Efter ett val anmäler KU vilande grundlagsbeslut för slutligt avgörande.

Vanliga moderna formuleringar:

    "antar slutligt det vilande förslaget"
    "slutligt antar förslaget"
    "slutligt antar förslagen"

Titlar innehåller ofta:

    "(vilande grundlagsbeslut)"

Men vi får INTE anta att en enda formulering fångar allt.

Sökningen bör därför göras i två riktningar.

## 6.1 Framåtriktad sökning

För varje första beslut:

    first_decision
        ->
    nästa riksdagsval
        ->
    KU:s eftervalsbehandling
        ->
    final_decision

## 6.2 Bakåtriktad sökning

Identifiera alla KU-betänkanden efter val som gäller:

    "vilande grundlagsbeslut"
    "slutligt"
    "förkastas"

Extrahera deras hänvisningar tillbaka till:

- första betänkandet
- första protokollet
- första riksdagsskrivelsen
- propositionen

Jämför sedan mängderna.

Om den framåtriktade och bakåtriktade sökningen hittar samma mängd första
beslut har vi en stark completeness-check.

# 7. Dokumentrelationer inom Riksdagens data

Bygg inte systemet runt fuzzy matching av titlar.

Modellera ett dokumentnätverk:

    proposition
        |
        v
    first_betankande
        |
        v
    first_decision / first_protocol
        |
        v
    first_rskr
        |
        v
    final_betankande
        |
        v
    final_decision / final_protocol
        |
        v
    final_rskr

Använd strukturerade metadatarelationer när de finns.

När de saknas, pars:a explicita dokumenthänvisningar ur text.

Exempel på mycket standardiserade referenser:

    prop. 2009/10:...
    bet. 2009/10:KU...
    prot. 2009/10:...
    rskr. 2009/10:...

Skapa gärna två typer av graph edges:

    structured_edge
    citation_edge

`structured_edge`:
relation uttryckligen tillhandahållen av Riksdagens data.

`citation_edge`:
relation extraherad ur dokumentets text.

Lagra provenance för varje edge.

# 8. Datamodell för ett grundlagsförslag

Förslag:

    constitutional_proposal
    -----------------------
    proposal_id
    constitution
    proposition_id
    first_bet_id
    first_protocol_id
    first_rskr_id
    first_decision_date
    first_decision_status
    final_bet_id
    final_protocol_id
    final_rskr_id
    final_decision_date
    final_status
    sfs_id
    notes
    confidence

`final_status` exempel:

    adopted
    rejected
    unresolved
    superseded
    conflicting_parallel_proposal
    data_missing

# 9. Ett mycket viktigt modernt negativt fall: 1991

Vi hittade ett uttryckligt modernt fall där ett vilande grundlagsförslag
förkastades efter valet.

Källa:

Betänkande 1991/92:KU13
"Vilande beslut om grundlagsändring, 11 kap. 15 § regeringsformen"

<https://www.riksdagen.se/sv/dokument-och-lagar/dokument/betankande/vilande-beslut-om-grundlagsandring-11-kap-15-s_gf01ku13/html/>

Bakgrund:

Första beslut:

    10 april 1991
    prop. 1990/91:65
    KU22
    rskr. 180

Förslaget gällde en ny:

    RF 11 kap. 15 §

Det var kopplat till EES och möjligheten/skyldigheten att inhämta
tolkningsbesked från en mellanfolklig domstol.

Efter att EES-avtalet förhandlats färdigt hade förutsättningarna ändrats.
Regeringen bedömde att bestämmelsen inte längre behövdes.

KU skrev uttryckligen att förslaget skulle förkastas.

Riksdagen biföll KU:s hemställan.

Statusdata anger bl.a.:

    protokoll 1991/92:44
    beslut 1991-12-12
    riksdagsskrivelse 1991/92:66

Detta är ett centralt testfall för programmet:

    first_decision = adopted_as_pending
    final_decision = rejected
    corresponding_SFS = none

Om skriptet inte hittar detta fall är recall för dålig.

# 10. Historiska exempel på förkastade vilande förslag

KU 2003/04:KU9 säger uttryckligen att det "vid flera tillfällen" förekom att
vilande grundlagsförslag förkastades vid det slutliga beslutet.

Källa:

<https://www.riksdagen.se/sv/dokument-och-lagar/dokument/betankande/forfattningsfragor_gr01ku9/html/>

## 10.1 1885 -> 1888: RF 6 §, nytt statsdepartement

1885 antogs ett förslag om ändring av RF 6 § som vilande.

Det gällde att gå från sju till åtta departementschefer och skapa ett nytt
departement för jordbruk/näringar/handel.

KU:s memorial 1888:

<https://www.riksdagen.se/sv/dokument-och-lagar/dokument/betankande/konstitutions-utskottets-memorial-no-1_cl10ku1/html/>

Riksdagsprotokoll 1888:

<https://www.riksdagen.se/sv/dokument-och-lagar/dokument/protokoll/1888-andra-kammaren-no-10_cl9o10/html/>

VIKTIG KORRIGERING:

Andra kammaren antog faktiskt förslaget 1888 med:

    133 ja
    62 nej

Men första kammaren hade förkastat det.

Därmed föll grundlagsändringen.

SOU 1899:1 sammanfattar historiken tydligt:

- 1885: båda kamrarna antog förslaget att vila
- 1887: slutbehandlingen sköts upp
- 1888: andra kammaren antog
- första kammaren förkastade
- frågan förföll

Källa:

<https://www.riksdagen.se/sv/dokument-och-lagar/dokument/statens-offentliga-utredningar/betankande-och-forslag_cwe01b2/html/>

Detta visar att datamodellen för tvåkammartiden måste kunna lagra beslut
per kammare.

## 10.2 1896 -> 1897: TF och straffregister

1896 antogs ett vilande förslag om ändring i:

    2 § 4:o tryckfrihetsförordningen

Det gällde utdrag ur det planerade straffregistret.

Vid slutbehandlingen den 17 mars 1897 röstade andra kammaren:

    77 ja
    134 nej

Förslaget förkastades.

Originalprotokoll:

<https://www.riksdagen.se/sv/dokument-och-lagar/dokument/protokoll/riksdagens-protokoll_cu9o15/html/>

Detta är ett utmärkt historiskt regressionstest.

# 11. Äldre sekundärlitteratur om förkastade grundlagsförslag

KU 2003/04:KU9 hänvisar till två äldre standardverk.

## 11.1 Robert Malmgren

Robert Malmgren,
"Riksdagen och lagstiftningen",
Stockholm 1934,
212 s.

Band XIV i:

    Sveriges riksdag:
    historisk och statsvetenskaplig framställning

KU hänvisar särskilt till:

    s. 137 f.

SvJT-recension med bibliografiska uppgifter:

<https://svjt.se/svjt/1935/354>

Svenskt biografiskt lexikon bekräftar också publikationen:

Robert Malmgren,
Riksdagen och lagstiftningen,
Stockholm 1934,
band XIV i Sveriges riksdag.

KU anger att Malmgren beskriver fall där vilande grundlagsförslag
förkastades vid slutligt beslut.

## 11.2 Nils Stjernquist

Nils Stjernquist,
"Riksdagens arbete och arbetsformer",
1966.

Del IV i:

    Samhälle och riksdag:
    historisk och statsvetenskaplig framställning

KU hänvisar särskilt till:

    s. 413-414

Sidan 413 gäller bl.a. hanteringen av vilande förslag.

Sidan 414 anges av KU som källa för historiska fall där vilande
grundlagsförslag förkastades.

Det är värt att få tag på s. 413-414 och Malmgren s. 136-138 och extrahera
alla historiska exempel därifrån.

Dessa böcker kan sökas via Libris, KB, Riksdagsbiblioteket och större
universitetsbibliotek.

# 12. Historisk skillnad före 1971

KU 2003/04:KU9 innehåller en viktig upplysning för text mining.

Före 1971 användes inte alltid termen "betänkande" för KU:s anmälan av
vilande grundlagsförslag.

KU:s dokument kunde vara:

    utlåtanden
    memorial

Anmälan av vilande grundlagsförslag gjordes fram till 1971 i form av
"memorial".

Efter 1971 används beteckningen "betänkande".

Det innebär att en historisk crawler som bara söker `doktyp=bet` kommer att
missa äldre fall.

# 13. SFS som andra huvudkälla

För varje slutligt antagen grundlagsändring bör det finnas en separat
ändringsförfattning i Svensk författningssamling.

Exempel:

    SFS 2022:1600
    Lag om ändring i regeringsformen

Regeringskansliets rättsdatabas visar exempelvis:

    SFS 2022:1600
    Omfattning: ändr. 7 kap. 7 §; omtryck
    Ikraft: 2023-01-01
    Förarbeten:
        Prop. 2021/22:40
        bet. 2021/22:KU12
        rskr. 2021/22:220
        bet. 2022/23:KU9
        rskr. 2022/23:25

Det är exakt den relation vi behöver.

Rättsdatabasen:

<https://rkrattsbaser.gov.se/sfsr/adv?sbet=1974%3A152>

Men projektet bör INTE vara beroende av scraping av denna databas om samma
information kan hämtas på bättre sätt.

# 14. Ändrings-SFS är viktigare än den konsoliderade SFS-versionen

Ett centralt designbeslut:

Försök INTE i första hand att skapa diff genom att jämföra två PDF-omtryck.

Problemet med omtryck:

- den konsoliderade texten visar hela grundlagen,
- ändringar kan markeras grafiskt med linje i vänstermarginal,
- det är dåligt maskinläsbart,
- det finns inte nödvändigtvis officiellt publicerade konsoliderade snapshots
  för varje historisk tidpunkt.

Använd i stället själva ändrings-SFS:en.

Exempel:

    Lag om ändring i regeringsformen

    ... föreskrivs att 7 kap. 7 § regeringsformen ska ha följande lydelse.

Detta är i praktiken en deklarativ patch.

# 15. Patch-typer som generatorn bör förstå

Minst:

    amend_section
    add_section
    repeal_section
    renumber_section
    add_chapter
    repeal_chapter
    rename_heading
    amend_heading
    replace_multiple_sections
    transitional_provision

Exempel på lagtekniska formuleringar:

    "X § ska ha följande lydelse"

    "X § ska upphöra att gälla"

    "nuvarande X § ska betecknas Y §"

    "det ska införas en ny X §"

    "X kap. ska ha följande lydelse"

    "rubriken närmast före X § ska ha följande lydelse"

Det kommer att finnas specialfall.

Försök därför INTE börja med en generell motor för alla svenska lagar.

Begränsa initialt motorn till:

    RF
    TF
    YGL
    SO

Mängden ändringsförfattningar är då hanterbar och specialfallen kan granskas
manuellt.

# 16. Datamodell för SFS-patchar

Förslag:

    sfs_amendment
    -------------
    sfs_id
    constitution
    issued_date
    effective_date
    source_url
    raw_text
    proposition_refs[]
    bet_refs[]
    rskr_refs[]

Och:

    sfs_operation
    -------------
    sfs_id
    sequence
    operation_type
    chapter
    section
    old_designation
    new_designation
    instruction_text
    new_text
    parser_confidence
    manually_verified

# 17. Generera historiska snapshots

Starta från en känd grundversion, t.ex.:

    RF @ 1975-01-01

Applicera ändrings-SFS kronologiskt.

Konceptuellt:

    base RF
       +
    amendment SFS A
       =
    RF version A
       +
    amendment SFS B
       =
    RF version B
       ...

Spara varje snapshot.

Exempel:

    constitution_version
    --------------------
    constitution
    valid_from
    triggering_sfs
    generated_text
    normalized_text
    checksum_raw
    checksum_normalized

# 18. Två sorters diff

Generera två olika diffar.

## 18.1 Juridisk/strukturell diff

Exempel:

    RF 2:24 amended
    RF 9:15 added
    RF 9:16 added
    RF 11:15 rejected before enactment

Detta är den viktigaste diffen för analys.

## 18.2 Textdiff

På paragraf-/styckenivå:

    old_text
    new_text

och eventuellt token-/word-diff:

    <del>...</del>
    <ins>...</ins>

En vanlig textdiff får INTE ensam avgöra juridisk identitet eftersom
omnumreringar och strukturändringar annars kan bli missvisande.

# 19. Ferenda/lagen.nu som teknisk källa och validator

Ny testversion:

<https://ferenda.lagen.nu/>

RF:

<https://ferenda.lagen.nu/1974:152>

OpenAPI:

<https://ferenda.lagen.nu/openapi.json>

Ferenda verkar exponera strukturerade dokument och historiska
versionsfunktioner/diff-funktioner.

Men:

FERENDAS HISTORISKA VERSIONER ÄR INTE KOMPLETTA BAKÅT I TIDEN.

Lagen.nu skrev när "Tidsmaskin för lagtext" lanserades 2019:

    historiken är inte fullständig för alla författningar

och att de flesta äldre versioner från ungefär de senaste 15 åren borde finnas.

Källa:

<https://lagen.nu/res/sitenews/1561421880>

För RF verkar den äldsta version som gränssnittet erbjuder vara knuten till:

    SFS 2002:925

Det bör tolkas som den äldsta historiska snapshot som lagen.nu/Ferenda har
för RF, INTE som den äldsta ändringen av RF.

# 20. Hur Ferenda bör användas

Använd INTE Ferenda som ensam historisk sanningskälla.

Använd det som:

1. strukturerad teknisk källa,
2. validator för vår egen versionsgenerator,
3. jämförelsepunkt från cirka början av 2000-talet och framåt.

För varje Ferenda-version:

    our_generated_version
          vs
    ferenda_version

Beräkna:

    exact_match
    normalized_match
    structural_match
    diff

# 21. Normalisering före jämförelse

Raw text kan skilja sig trots identisk juridisk lydelse.

Normalisera exempelvis:

- Unicode
- whitespace
- radbrytningar
- icke-brytande mellanslag
- paragraftecken
- typografiska citattecken
- OCR-artefakter där det är säkert
- HTML-markup
- fotnoter/annoteringar
- sidhuvuden/sidnummer

Jämför helst på struktur:

    chapter
      -> section
          -> paragraph

Spara både rå och normaliserad text.

Ändra aldrig originaltexten permanent; normalisering ska vara ett separat lager.

# 22. Ferenda som "test oracle"

Om vår generator reproducerar Ferendas konsoliderade RF exakt eller
strukturellt från ca 2002 framåt ger det stark evidens för att patchmotorn
fungerar.

Vid avvikelse:

1. hitta första snapshot där checksums skiljer sig,
2. identifiera triggering SFS,
3. jämför patchtolkningen,
4. avgör om:
   - vår parser är fel,
   - Ferenda är fel,
   - textnormaliseringen är fel,
   - en ändring har flera ikraftträdandedatum,
   - en specialregel har missats.

Ferenda ska alltså vara validator, inte facit.

# 23. Varför historiska konsolideringar saknas

Viktig historisk källa:

    Ds 1998:10
    Ett offentligt rättsinformationssystem

Riksdagen:

<https://www.riksdagen.se/sv/dokument-och-lagar/dokument/departementsserien/ett-offentligt-rattsinformationssystem_gmb410/html/>

Lagen.nu:

<https://lagen.nu/ds/1998%3A10>

Regeringen:

<https://www.regeringen.se/rattsliga-dokument/departementsserien-och-promemorior/1998/01/ds-199810/>

Ds 1998:10 beskriver problemet mycket tydligt.

Vid denna tid fanns konsoliderade författningar elektroniskt, men det saknades
en generell funktion för att få fram äldre lydelser av bestämmelser i SFS.

Arbetsgruppen föreslog därför uttryckligen att när en SFS-bestämmelse
upphävdes skulle den sparas elektroniskt så att det blev möjligt att
rekonstruera grundförfattningars lydelse vid tidigare tidpunkter.

Detta är historiskt viktigt för projektet:

Vår generator löser i praktiken exakt det versionsproblem som staten redan
identifierade på 1990-talet.

# 24. Koppla slutligt riksdagsbeslut till SFS

Idealfallet är att ändrings-SFS själv innehåller förarbeteshänvisningar.

Exempel:

    SFS 2022:1600

kan länkas till:

    Prop. 2021/22:40
    bet. 2021/22:KU12
    rskr. 2021/22:220
    bet. 2022/23:KU9
    rskr. 2022/23:25

Detta ger:

    proposition
        ->
    first bet
        ->
    first rskr
        ->
    final bet
        ->
    final rskr
        ->
    SFS

För moderna ändringar kan denna kedja vara explicit.

# 25. Matchningshierarki mellan riksdagsärende och SFS

Använd i denna ordning:

1. explicit betänkande-ID i SFS/förarbetesmetadata
2. explicit riksdagsskrivelse-ID
3. explicit proposition-ID
4. exakt lagtitel
5. berörda paragrafer
6. besluts-/utfärdandedatum
7. ikraftträdandedatum
8. lagtext
9. fuzzy matching endast som sista utväg

Varje matchning bör få:

    match_method
    confidence
    evidence[]

# 26. Tvåvägsvalidering

Detta är centralt.

## A. Riksdagen -> SFS

För varje:

    first pending decision

hitta:

    final decision

Om:

    final_status = adopted

ska motsvarande ändrings-SFS normalt kunna identifieras.

Om:

    final_status = rejected

ska ingen sådan SFS finnas.

## B. SFS -> Riksdagen

Hämta samtliga ändrings-SFS för:

    RF
    TF
    YGL
    SO

och extrahera deras:

    prop.
    bet.
    rskr.

Kontrollera att varje SFS kan kopplas till ett giltigt slutligt
grundlagsbeslut.

De två traversalernas resultat bör överensstämma.

# 27. Negativa fall är särskilt värdefulla

Systemet ska uttryckligen kunna representera:

    pending proposal
       ->
    final rejection
       ->
    NO SFS

1991/92:KU13 är det viktigaste moderna regressionstestet.

1885/1888 och 1896/1897 är viktiga historiska regressionstest.

# 28. Specialproblem före enkammarriksdagen

Före 1971 fanns två kamrar.

Ett slutligt grundlagsförslag kunde därför exempelvis:

    First Chamber = reject
    Second Chamber = adopt

och ändå falla.

Exempel:

    RF 6 §, 1888

Datamodellen bör därför för äldre data ha:

    chamber_decision
    ----------------
    proposal_id
    chamber
    decision_date
    vote_yes
    vote_no
    result

och sedan:

    aggregate_final_status

För enkammarriksdagen räcker normalt ett kammarresultat.

# 29. Specialproblem: alternativa och motstridiga vilande förslag

KU 2003/04:KU9 beskriver äldre praxis där flera alternativa eller
oförenliga vilande grundlagsförslag kunde existera parallellt.

Det innebär att man INTE alltid kan anta:

    one paragraph -> one pending proposal

Proposal-ID måste därför representera själva lagförslaget, inte bara
grundlag + paragraf.

Modellera relationer som:

    conflicts_with
    supersedes
    alternative_to

# 30. Ändrings-SFS och omtryck

Exempel SFS 2022:1600 är märkt "Omtryck".

Det betyder att SFS-dokumentet kan innehålla hela RF efter ändringen även om
den juridiska ändringen bara gäller t.ex.:

    7 kap. 7 §

Parsern måste därför skilja mellan:

    amendment instruction

och:

    republished consolidated text

Annars riskerar systemet att tro att varje paragraf i omtrycket ändrades.

Ingress/omfattningsmetadata är därför viktigare än mängden text i PDF:en.

# 31. Regeringens rättsdatabaser

Regeringskansliets rättsdatabaser är mycket användbara som kontrollkälla.

Exempel RF:

<https://rkrattsbaser.gov.se/sfsr/adv?sbet=1974%3A152>

Den listar bl.a.:

- SFS-nummer
- rubrik
- omfattning
- ikraftträdande
- förarbeten

Exempel:

    SFS 2022:1565
    ändr. 2 kap. 24 §

    Prop. 2021/22:42
    bet. 2021/22:KU13
    rskr. 2021/22:221
    bet. 2022/23:KU4
    rskr. 2022/23:9

och:

    SFS 2022:1566
    ändr. 8 kap. 13 §,
           9 kap. 13, 14 §§;
           nya 9 kap. 15, 16 §§

samt:

    SFS 2022:1600
    ändr. 7 kap. 7 §;
    omtryck

Problemet:

Det verkar inte finnas ett bekvämt modernt publikt API för allt detta.

Undvik därför att göra systemet beroende av HTML-scraping där det går.

Använd rättsdatabasen som:

    validation / fallback / audit source

# 32. Regeringen.se:s "lagstiftningskedja"

Regeringen.se visar ofta:

    proposition
    utskottsbehandling
    beslut
    SFS

på sina propositionssidor.

Men informationen ligger i webbsidornas HTML och bör inte vara primär
maskinell källa om vi kan rekonstruera relationerna från:

    Riksdagens öppna data
    +
    SFS/Ferenda

Använd regeringen.se främst för manuell verifiering.

# 33. Föreslagen pipeline

## Phase 1: Riksdagsdataset

1. Hämta KU-dokument för perioden 1975-idag.
2. Fulltextsök efter vilande grundlagsbeslut.
3. Extrahera första beslut.
4. Extrahera eftervalsbehandling.
5. Pars:a prop/bet/prot/rskr-referenser.
6. Bygg document graph.
7. Klassificera final status.

## Phase 2: SFS-index

För varje av de fyra grundlagarna:

1. identifiera alla ändrings-SFS,
2. hämta:
   - SFS-ID
   - titel
   - datum
   - ikraft
   - omfattning
   - förarbeten
3. länka till riksdagsgraphen.

## Phase 3: patch parser

För varje ändrings-SFS:

1. identifiera ändringsinstruktionen,
2. pars:a operationer,
3. spara strukturerade operations,
4. applicera på föregående snapshot.

## Phase 4: version generator

Generera:

    version_0
    version_1
    version_2
    ...

med checksums.

## Phase 5: Ferenda validation

För varje Ferenda-snapshot som finns:

1. hämta motsvarande version,
2. normalisera båda,
3. jämför,
4. logga avvikelser.

## Phase 6: completeness audit

Kör:

    first decisions -> final decisions -> SFS

och:

    SFS -> final decisions -> first decisions

Rapportera alla orphan records.

# 34. Föreslagna QA-regler

Flagga automatiskt om:

    final_status == adopted AND sfs_id IS NULL

Flagga om:

    final_status == rejected AND sfs_id IS NOT NULL

Flagga om:

    sfs_id IS NOT NULL AND final_bet_id IS NULL

Flagga om:

    first_decision_date > final_decision_date

Flagga om:

    inget riksdagsval ligger mellan first och final

Flagga om:

    proposal text differs materially between first and final

Flagga om:

    generated Ferenda-era snapshot != Ferenda normalized snapshot

Flagga om:

    amendment parser encounters unknown legislative instruction

# 35. Regressionstest: minimum

Skriv automatiserade tester för åtminstone:

## Test A: 1991 rejection

Input:

    prop. 1990/91:65
    first decision 1991-04-10
    RF new 11:15

Expected:

    final_bet = 1991/92:KU13
    final_date = 1991-12-12
    final_status = rejected
    final_rskr = 1991/92:66
    sfs = null

## Test B: SFS 2022:1600

Expected:

    constitution = RF
    operation = amend
    target = 7:7
    final_bet = 2022/23:KU9
    final_rskr = 2022/23:25
    effective = 2023-01-01

Omtrycket får INTE tolkas som att hela RF ändrades.

## Test C: 1896/1897 TF

Expected:

    pending_from = 1896
    target = TF 2 § 4:o
    final_vote_second_chamber_yes = 77
    final_vote_second_chamber_no = 134
    final_status = rejected

## Test D: 1885/1888 RF 6

Expected:

    first_pending = 1885
    target = RF § 6
    first_chamber_final = rejected
    second_chamber_final = adopted
    second_chamber_vote = 133-62
    aggregate_final_status = rejected

# 36. Källhierarki

För juridiska fakta bör prioriteten vara ungefär:

1. original-SFS / officiell SFS
2. riksdagens originaldokument och beslut
3. Riksdagens öppna data/statusmetadata
4. Regeringskansliets rättsdatabaser
5. SOU/Ds och officiella historiska sammanställningar
6. Ferenda/lagen.nu
7. juridisk sekundärlitteratur

Ferenda kan vara tekniskt mycket bättre än vissa officiella gränssnitt men är
inte den officiella rättskällan.

Lagra därför alltid provenance.

# 37. Provenance-modell

Varje faktauppgift bör helst kunna spåras.

Exempel:

    evidence
    --------
    entity_type
    entity_id
    field
    value
    source_type
    source_url
    source_document_id
    extraction_method
    extraction_timestamp
    confidence

Exempel:

    final_status = rejected
    source = 1991/92:KU13
    extraction_method = exact_phrase
    confidence = 1.0

# 38. Saker vi INTE bör göra

Undvik:

- att anta att varje KU-betänkande är själva riksdagsbeslutet,
- att använda bara ordet `vilande`,
- att använda bara moderna stavningar för 1800-talsmaterial,
- att anta att Ferendas versionslista är komplett före ca 2000-talet,
- att diff:a omtryckta PDF:er som primär metod,
- att tolka hela texten i ett omtryck som ändrad,
- att använda proposition-ID som enda join key,
- att anta att en proposition motsvarar exakt en grundlagsändring,
- att anta att en paragraf bara kan ha ett vilande förslag,
- att anta att alla historiska dokument heter "betänkande",
- att anta att metadata är komplett bara för att API:t returnerar ett objekt.

# 39. Möjlig slutprodukt

Om allt fungerar får vi något som i praktiken liknar ett Git-repository för
svenska grundlagar:

    RF/
      1975-01-01
      ...
      1992-...
      ...
      2023-01-01

Varje commit kan representeras av:

    SFS
    date
    effective_date
    changed_provisions
    patch
    old_text
    new_text
    proposition
    first_bet
    first_decision
    final_bet
    final_decision
    rskr
    source_links

Dessutom kan failed proposals ligga som "unmerged branches":

    proposal 1990/91:65
      -> first adopted
      -> election
      -> rejected
      -> never enters constitution history

Detta är analytiskt mycket användbart.

# 40. Viktiga källor att börja med

## Grundlagsprocess/historik

KU 2003/04:KU9, Författningsfrågor:
<https://www.riksdagen.se/sv/dokument-och-lagar/dokument/betankande/forfattningsfragor_gr01ku9/html/>

Detta dokument innehåller bl.a.:

- historik tillbaka till 1766,
- regler under 1809 års RF,
- äldre riksdagsordning,
- memorial/betänkande-distinktionen,
- hänvisning till Malmgren,
- hänvisning till Stjernquist,
- uttrycklig uppgift om att vilande förslag historiskt har förkastats.

## Modernt förkastat förslag

1991/92:KU13:
<https://www.riksdagen.se/sv/dokument-och-lagar/dokument/betankande/vilande-beslut-om-grundlagsandring-11-kap-15-s_gf01ku13/html/>

## Historiskt förkastat förslag 1897

Riksdagens protokoll 1897:15:
<https://www.riksdagen.se/sv/dokument-och-lagar/dokument/protokoll/riksdagens-protokoll_cu9o15/html/>

## Historiskt förslag 1885/1888

KU memorial 1888:
<https://www.riksdagen.se/sv/dokument-och-lagar/dokument/betankande/konstitutions-utskottets-memorial-no-1_cl10ku1/html/>

Andra kammarens protokoll:
<https://www.riksdagen.se/sv/dokument-och-lagar/dokument/protokoll/1888-andra-kammaren-no-10_cl9o10/html/>

SOU 1899:1 som sammanfattar utfallet:
<https://www.riksdagen.se/sv/dokument-och-lagar/dokument/statens-offentliga-utredningar/betankande-och-forslag_cwe01b2/html/>

## Riksdagens öppna data

<https://www.riksdagen.se/sv/dokument-och-lagar/riksdagens-oppna-data/>

<https://www.riksdagen.se/sv/dokument-och-lagar/riksdagens-oppna-data/anvandarstod/>

<https://www.riksdagen.se/sv/dokument-och-lagar/riksdagens-oppna-data/anvandarstod/sa-fungerar-dokument-id/>

## Regeringskansliets rättsdatabas, RF

<https://rkrattsbaser.gov.se/sfsr/adv?sbet=1974%3A152>

## Ds 1998:10

Riksdagen:
<https://www.riksdagen.se/sv/dokument-och-lagar/dokument/departementsserien/ett-offentligt-rattsinformationssystem_gmb410/html/>

Lagen.nu:
<https://lagen.nu/ds/1998%3A10>

Regeringen:
<https://www.regeringen.se/rattsliga-dokument/departementsserien-och-promemorior/1998/01/ds-199810/>

## Ferenda/lagen.nu

<https://ferenda.lagen.nu/>

<https://ferenda.lagen.nu/1974:152>

<https://ferenda.lagen.nu/openapi.json>

Historik/tidsmaskin:
<https://lagen.nu/res/sitenews/1561421880>

## Robert Malmgren

Robert Malmgren,
Riksdagen och lagstiftningen,
Stockholm 1934,
Sveriges riksdag XIV.

Relevant:
s. 136-138, särskilt 137 f.

SvJT:
<https://svjt.se/svjt/1935/354>

## Nils Stjernquist

Nils Stjernquist,
Riksdagens arbete och arbetsformer,
Samhälle och riksdag IV,
1966.

Relevant:
s. 413-414.

# 41. Rekommenderad första implementation

Börja INTE med PDF-parsern.

Första MVP:

1. endast RF,
2. endast 1975-idag,
3. hämta KU-betänkanden från Riksdagens öppna data,
4. hitta alla `vilande`-ärenden,
5. bygg first/final decision pairs,
6. verifiera att 1991/92:KU13 identifieras som rejection,
7. skapa lista över alla slutligt antagna RF-ändringar,
8. koppla dem till SFS,
9. först därefter bygg patchmotorn,
10. validera genererade versioner mot Ferenda från ca 2002 framåt.

När RF fungerar:

    add TF
    add YGL
    add SO

När 1975-idag fungerar:

    extend backwards to 1971
    then 1867+
    then potentially 1809-1866 via other digitized sources.

# 42. Viktig forskningshypotes

Den ursprungliga hypotesen var ungefär:

    "I modern tid har andra grundlagsbeslutet alltid varit en formalitet."

Den är FEL i strikt mening.

1991/92:KU13 visar ett klart modernt motexempel.

En bättre empirisk fråga är:

    Hur ofta har ett vilande grundlagsförslag förkastats vid den slutliga
    behandlingen, och när skedde det senast?

Det dataset vi bygger bör kunna besvara detta exakt utan att förlita sig på
sekundärlitteratur.

# 43. Önskad slutrapport från skriptet

Exempel:

    total_pending_proposals: N
    finally_adopted: N
    finally_rejected: N
    unresolved: N
    matched_to_sfs: N
    adopted_without_sfs_match: N
    orphan_sfs: N

Och:

    rejected:
      - 1990/91:65 -> 1991/92:KU13 -> rejected
      - ...

    validation:
      ferenda_snapshots_checked: N
      exact_matches: N
      normalized_matches: N
      mismatches: N

Dessutom CSV/JSON med en rad per individuellt grundlagsförslag.

# 44. Kärnprincip

Separera alltid tre saker:

    POLITICAL/LEGISLATIVE PROPOSAL
              |
              v
       PARLIAMENTARY DECISIONS
              |
              v
          ENACTED SFS

Ett första vilande beslut är inte lag.

Ett slutligt beslut är den parlamentariska förutsättningen för lag.

Ändrings-SFS är den promulguerade ändringen.

En historisk konsoliderad grundlag är resultatet av att alla relevanta
ändrings-SFS applicerats i rätt ordning och med rätt ikraftträdandedatum.

Det är den modellen som bör styra hela implementationen.
