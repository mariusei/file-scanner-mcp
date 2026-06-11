# M2c forhåndsregistrerte forventninger (skrevet FØR focus= er implementert)

Dato: 2026-06-11. Skrevet og committet før første linje av `focus=`-
implementasjonen og før noen episode er kjørt.

## Hva som testes

`scan_file(focus=NODE)`: fil-skjelett på dybde 1 + fokusert node verbatim
med linjenumre. Hypotesen er at strukturell adressering av lesesteget
(«les denne funksjonen») gir riktigere kroppsnivå-svar enn linje-/range-
gjetting med sed/cat.

## Design

- 8 oppgaver (`m2c_tasks.json`) der fasit-faktaene ligger **inni
  funksjonskropper** (betingelser, returverdier, exception-mapping) —
  verifisert til stede ved base_commit/nåværende commit før preregistrering
- 2 armer, identiske bortsett fra focus:
  - **Arm A (før):** scantool-CLI (preview/scandir/scanfile/search/searchname,
    v2-beskrivelser) + sed/cat/head/tail via wrapper
  - **Arm B (etter):** samme + `focusread PATH NODE`
- 2 repetisjoner per celle → 32 episoder, én fersk haiku-subagent per
  episode, maks 6 verktøykall, all output logget ved konstruksjon
- Gradering: fakta fra m2c_tasks.json funnet i hele sluttmeldingen
  (semantisk ekvivalens godtas, f.eks. «303» = «see_other»). Konvensjon
  avviker fra M2b: faktaene er deskriptive kriterier, ikke navnetokens,
  fordi kroppsnivå-fakta ikke er greppbare enkeltord.

## Forhåndsregistrerte utfall

**P1 — forventet (primær, korrekthet):** Arm B har fakta-dekning ≥ 10
prosentpoeng over arm A. (28 fakta × 2 reps = 56 graderbare per arm.)
Differanse < 5 pp regnes som null gitt n.

**P2 — sekundær (lese-tokens):** Loggede tokens fra *lesesteget*
(sed/cat/focusread-output) er ≥ 20 % lavere i arm B. M2b-lærdom: totale
tokens er upålitelig margin; bare lesesteget er hypotesens domene.

**P3 — null (discoverability):** Hvis focusread brukes i < 50 % av
arm B-episodene, er funnet et styrings-/beskrivelsesproblem, ikke et
kapabilitetsfunn. Da re-kjøres arm B én gang med justert
kommandobeskrivelse (dokumentert som v2, jf. M2b → M2b-v2), og BEGGE
kjøringene rapporteres.

**P4 — null (redundans):** Hvis arm A når ≥ 85 % dekning, viser
skjelett+sed-flyten seg tilstrekkelig for kroppsnivå-spørsmål, og
focus= bør skrinlegges uavhengig av P1. Gyldig og verdifullt utfall.

**P5 — paradoks (tunnelsyn):** Arm B kan få *lavere* dekning hvis presis
nodelesing frister agenten til å hoppe over skjelettkonteksten og
feilankre (flask-5063-mønsteret fra M2b). Kjennes igjen ved: flere
feilankre (feil fil/funksjon i sluttmeldingen) i arm B enn A.

## Antagelser (eksplisitte)

- Haiku-agenter klarer å oppgi node-stier (ClassA.method) fra
  scanfile/search-output — hvis ikke, er det et reelt produktfunn, ikke støy
- Fasiten er entydig; semantiske tvetydigheter à la sg-T4 (TTL=None)
  noteres og ekskluderes fra differansen hvis de oppstår
- 2 reps skiller ikke støy fra liten effekt; alt under 5 pp rapporteres
  som «ikke skillbart fra null», ikke som retning

## Hva som ville overraske mest

At arm B bruker focusread flittig OG får lavere dekning enn arm A — det
ville falsifisere selve premisset om at presis lesing er flaskehalsen,
og peke på at *utvelgelsen* (hvilken node å lese) er den egentlige
flaskehalsen.

---

# M2c-v2 forhåndsregistrert (2026-06-11, skrevet FØR v2-episodene)

Tester STYRINGSEFFEKTEN av den nye lesesteg-styringen (commit 5a0300e)
isolert: arm B re-kjøres med én tilføyd styringslinje i episodeprompten
som speiler produksjons-instructions («les én funksjon → focusread,
aldri helfils-cat/sed-gjetting»). Alt annet identisk med arm B v1.
Kanal-forbehold: prompten er proxy for MCP server instructions —
eksperimentet måler tekstens effekt, ikke injeksjonskanalen.

16 episoder (8 oppgaver × 2 reps). Baseline (arm B v1): focusread i
9/16 episoder, 13 523 lese-tokens, 53/53 fakta.

**V1 — forventet:** focusread-andel ≥ 12/16 (75 %), lese-tokens ≤ v1-
nivå, dekning holder (≥ 95 %).

**V2 — null (redundans i styring):** andel innenfor 9/16 ± 2 — én
linje ekstra styring endrer ikke adferd når kommandolisten alt nevner
verktøyet; da er discoverability-flaskehalsen et kapabilitets-/
oppgavetrekk, ikke et tekstproblem.

**V3 — paradoks (overstyring):** focusread brukes også der search
allerede viste kroppen → flere kall og HØYERE totaltokens enn v1
(> +20 %). Styring som ikke er oppgavebetinget koster (sg-T5-lærdommen
fra M2b-v2).

**Støygulv:** n=16; bare skift på ≥ 3 episoder i andel er skillbart
fra støy. Dekning graderes med samme konvensjon som M2c.
