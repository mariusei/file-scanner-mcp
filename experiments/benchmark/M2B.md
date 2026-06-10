# M2b: Ekte agent-episoder — resultater (2026-06-11)

22 episoder: 11 oppgaver × 2 verktøysett, én fersk haiku-subagent per
episode, maks 6 verktøykall, all verktøyoutput logget gjennom wrapper
(måling ved konstruksjon). Forhåndsregistrerte forventninger i
`/tmp/m2b/PREREGISTRERT.md`, skrevet før første episode.

## Hovedtall

| | grep-agenter | scantool-agenter |
|---|---|---|
| Fakta-dekning i svar | 24/33 (**73 %**) | 29/33 (**88 %**) |
| Verktøykall totalt | 64 | 60 |
| Loggede verktøy-tokens | **61 027** | 91 128 |
| Totale agent-tokens | **249 872** | 329 092 |

## Forventning 1 FALSIFISERT — og det er hovedfunnet

Forhåndsregistrert: «scantool-agenter med ≥2× færre loggede tokens».
Resultat: scantool-agentene brukte **1,5× FLERE**. Forklaringen er
forskjellen mellom det harnessen måler og det agenter gjør:

- Harnessen måler tokens TIL fakta er synlige (tidlig stopp)
- Ekte agenter stopper ved *subjektiv sikkerhet*, ikke ved fakta-dekning —
  og scantools rike outputs (preview ≈ 4–5k tokens, scandir ≈ 2k)
  INVITERER til konsum. Ingenting presser agenten til å bruke budget-
  skiven; den kanoniske trakten finnes i verktøybeskrivelsene, men
  CLI-prompten håndhevet den ikke

## Forventning 2 BEKREFTET: korrekthet

scantool-agentene ga målbart bedre svar (88 % vs 73 % fakta-dekning):

- **sg-T1**: scantool navnga begge trigger-funksjonene med linjenumre
  (run_model_calculation@381, delete_model@878) + en presis negativ
  observasjon (datasets/indicators bruker TTL, ikke invalidering);
  grep-agenten ga bare filen og prosa
- **sg-T5 (arkitektur)**: scantool 5/5 fakta (startup_validation, get_pool,
  health_check navngitt); grep 2/5
- **requests-2674**: scantool svarte adapters.py (= gullpatchen);
  grep ankret i models.py — feil fil
- **Ærlig tap, flask-5063**: scantool-agenten fulgte strukturen til
  wrappers.py (plausibelt men feil); grep fant cli.py

## Konklusjoner

1. **Marginen som overlever ekte agenter er KORREKTHET, ikke tokens.**
   «Kan ikke matches»-påstanden må omformuleres: scantool gir riktigere
   og mer fullstendige svar (færre feilankre, navngitte funksjoner og
   linjenumre), men token-fordelen realiseres bare med tidlig stopp eller
   budsjettpress — ubegrensede agenter konsumerer det de serveres.
2. **Produktsignal**: rike defaults trenger konsum-styring for agenter —
   preview (4–5k) som førstevalg er dyrt i agenters hender; budget-
   presets og glimt-første-flyt må være det verktøybeskrivelsene dytter
   mot. (Token-allokering påvirker oppfattet viktighet — og output-
   rikdom påvirker konsum.)
3. **Modellnivå**: haiku-agenter fulgte reglene (logg-verifisert i
   stikkprøver; ikke fullautomatisert per episode — dokumentert svakhet)
   og klarte begge verktøysett godt; verktøyforskjellen viste seg i
   svarkvalitet, ikke i evne til å bruke verktøyene.

## Avvik og svakheter

- flask-4045-scan krasjet (API-feil) og ble re-kjørt; loggen inneholder
  ~2 kall fra det døde forsøket (scan-tallene marginalt inflaterte)
- Gradering på hele sluttmeldingen (ikke kun ANSWER-linjen), én gradering
  (ingen inter-rater), én kjøring per celle
- sg-T4 avdekket en semantisk tvetydighet begge verktøysett arvet:
  TTL=None tolkes som «cacher evig» (grep-agent) vs «cacher ikke»
  (scantool-agent) — fasiten skiller ikke
