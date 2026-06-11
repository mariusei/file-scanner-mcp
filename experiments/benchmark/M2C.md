# M2c: focus= mot kroppsnivå-spørsmål — resultater (2026-06-11)

32 episoder: 8 oppgaver × 2 armer × 2 reps, én fersk haiku-subagent per
episode, maks 6 verktøykall, all wrapper-output logget ved konstruksjon.
Forventninger preregistrert og committet FØR implementasjon og episoder
(`M2C_preregistrert.md`, commit 51ebaa5). Armene var identiske bortsett
fra `focusread PATH NODE` i arm B. Rålogger: `m2c/logs/`, sluttmeldinger:
`m2c/answers-*.md`, analyse: `m2c/analyze_logs.py`.

## Observasjoner (rå tall, ingen tolkning)

| | Arm A (uten focus) | Arm B (med focus) |
|---|---|---|
| Fakta-dekning | 56/56 (100 %) | 53/53 (100 %)* |
| Wrapper-kall totalt | 65 | 73 |
| Lese-tokens (cat/sed/focusread-output) | 54 337 | 13 523 |
| Navigasjons-tokens | 34 679 | 31 165 |
| Sum verktøy-tokens | 89 016 | 44 688 |
| Episoder med focusread-bruk | — | 9/16 (56 %) |
| Feilankre (feil fil/funksjon i svar) | 0 | 0 |

*Én arm B-episode (pytest-7373-b-r2) er ekskludert: 9 rapporterte
verktøykall mot 2 loggede — 7 kall skjedde utenfor wrapperne, og svaret
(3/3 fakta) kan ikke attribueres til logget verktøyoutput. Inkludert
ville arm B vært 56/56.

Største enkelt-lesinger: arm A inneholdt tre helfils-cat på 9 248,
11 382 og 15 210 tokens; arm Bs største lesing var 2 598 tokens.

## De preregistrerte utfallene mot data

**P1 (korrekthet, ≥10 pp differanse): IKKE innfridd — takeffekt.**
Begge armer traff 100 %. Differansen er 0, under null-grensen på 5 pp.
Oppgavene var for lette for haiku med begge verktøysett til å skille
armene på korrekthet.

**P2 (lese-tokens ≥20 % lavere i arm B): INNFRIDD med stor margin.**
−75 % (13 523 mot 54 337). Mekanismen er synlig i råloggene: uten focus
faller agenter tilbake til helfils-cat eller brede sed-ranges; med focus
leses noden presist. Merk at P2 var preregistrert som sekundær.

**P3 (discoverability, focusread i ≥50 % av episodene): INNFRIDD, så
vidt.** 9/16 (56 %). Ingen re-kjøring med justert beskrivelse nødvendig,
men marginen er tynn — 7 episoder løste oppgaven uten focusread, oftest
fordi search/searchname allerede viste kroppen.

**P4 (null-redundans, arm A ≥85 %): INNFRIDD — og dette er hovedfunnet
sammen med P2.** Skjelett+search+sed-flyten var TILSTREKKELIG for
korrekthet på alle kroppsnivå-spørsmålene. Preregistreringen sa at P4
alene tilsier skrinlegging «uavhengig av P1» — men den formuleringen
antok at dekning var eneste margin og foregrep ikke kombinasjonen
P4+P2 begge sanne. Spenningen rapporteres som den er, se konklusjon.

**P5 (paradoks/tunnelsyn): IKKE observert.** Null feilankre i begge
armer; focus-lesing førte ikke til at skjelettkonteksten ble hoppet over.

## Konklusjoner [TOLKNING — eksplisitt merket]

1. **Korrekthetsmarginen fra M2b reproduserte IKKE på kroppsnivå-
   oppgaver — fordi begge armer traff taket.** Scantools eksisterende
   outputs (search med strukturell kontekst, salient skjelett med full
   dybde) leverer allerede kroppsnivå-fakta oftere enn antatt. Det er
   et redundans-funn, ikke et focus-funn.
2. **Marginen som overlevde er lesesteg-økonomi, ikke korrekthet:**
   samme dekning til 75 % lavere lesekostnad og halvert total
   verktøykostnad. M2b-lærdommen («ubegrensede agenter konsumerer det
   de serveres») gjentok seg speilvendt: uten presis lesevei konsumerer
   agenter hele filer for å være sikre.
3. **Beslutning iht. preregistreringen:** P4-regelen («skrinlegg») ble
   utløst, men gjaldt eksplisitt premisset om dekning som margin; P2
   (sekundær, preregistrert) ble innfridd kraftig. Ærlig lesning:
   focus= er IKKE begrunnet som korrekthetstiltak på dette
   oppgavesettet, men er begrunnet som kostnadstiltak. Beholdes med
   den begrunnelsen — og bør re-testes på oppgaver der taket ikke nås
   (større filer, svakere modell, eller spørsmål som krever flere
   noder per fil) før korrekthetsgevinst påstås.

## Addendum: M2c-v2 — styringseffekten av lesesteg-teksten (2026-06-11)

Arm B re-kjørt med én tilføyd styringslinje i prompten som speiler de nye
produksjons-instructions (commit 5a0300e): «To READ one function/class/
section located by a scan or search: use focusread … Never cat a whole
file or sed a guessed line range.» Alt annet identisk. Preregistrert i
M2C_preregistrert.md (commit d166e16, FØR episodene). 16 episoder.

| | Arm B v1 | Arm B2 (ny styring) |
|---|---|---|
| Episoder med focusread | 9/16 (56 %) | **13/16 (81 %)** |
| Wrapper-kall | 73 | 59 |
| Lese-tokens | 13 523 | 15 944 |
| Navigasjons-tokens | 31 165 | 18 269 |
| Sum verktøy-tokens | 44 688 | **34 213 (−23 %)** |
| Fakta-dekning | 53/53 (100 %) | 54/56 (96 %) |

Mot de preregistrerte v2-utfallene:

- **V1 (forventet): i hovedsak innfridd.** Andel 81 % ≥ 75 %-terskelen,
  skiftet (+4 episoder) er over støygulvet (≥3); dekning 96 % ≥ 95 %.
  Forbehold: lese-tokens ble IKKE ≤ v1 (+18 %) — flere episoder leste
  noden i stedet for å svare rett fra skjelettet. Det kjøpte til
  gjengjeld 41 % færre navigasjons-tokens (færre leterunder), så
  totalen falt 23 %.
- **V2 (null/redundans): forkastet** — teksten flyttet adferd.
- **V3 (paradoks/overstyring): ikke utløst** — færre kall (59 mot 73)
  og lavere total; ingen tvangsmessig focusread der search alt svarte
  (3 episoder hoppet fortsatt over lesing, korrekt).

[TOLKNING] Styringslinjen gjør det den skal: focusread-andelen opp
56 → 81 %, totalkostnad ned ytterligere 23 % (mot arm A: −62 %). M2b-
lærdommen bekreftes en tredje gang: beskrivelsesteksten er spaken.
Kanal-forbehold står: prompt-styring er proxy for MCP-instructions —
injeksjonskanalen i produksjon er ikke direkte testet.

Ærlig svakhet: én v2-episode (pytest-5221-b2-r1) FEILET helt (0/2) —
agenten fant aldri funksjonen (gjettet feil fil), brukte opp kallene og
svarte vagt fra forkunnskap. Første dekningssvikt i hele M2c. Styring
av lesesteget kompenserer ikke for lokaliseringssvikt; med n=16 kan det
være støy, men det viser at 100 %-taket ikke er garantert.

## Avvik og svakheter

- pytest-7373-b-r2 kontaminert (7 uloggede kall) — ekskludert; trolig
  delvis besvart fra modellens forkunnskap om den kjente pytest-bugen
- sg-jwt-b-r1 brukte find/grep via wrapperen i strid med kommandolisten
  (alt logget, så målingene er intakte); 3 episoder brukte 7–8 kall mot
  regelen om 6; ±1–2 kall-avvik i flere episoder skyldes trolig
  CLI-krasj før logging (arg-feil logges ikke)
- Takeffekten betyr at oppgavesettet ikke kan skille armene på
  korrekthet — P1 er ubesvart, ikke falsifisert
- Én gradering (ingen inter-rater), 2 reps, semantisk gradering av
  deskriptive fakta (mer skjønn enn M2bs token-fakta)
- Grader (samme modellfamilie som agentene) kjente hypotesen
