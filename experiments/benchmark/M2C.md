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
