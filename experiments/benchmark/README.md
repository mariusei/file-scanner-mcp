# M2-benchmark: informasjonsleverings-effektivitet

**Spørsmålet:** kan scantool i praksis matches av grep + filesing? Målt som
tokens og verktøykall til alle fasit-fakta for en oppgave er synlige i
akkumulert verktøyoutput, under kanoniske (dokumenterte, kritiserbare)
strategier per verktøysett. Kjør: `uv run --with tiktoken python
experiments/benchmark/harness.py`

## Resultater (internal-backend backend, 2026-06-10)

| Oppgave | scantool | grep-baseline | Margin |
|---|---|---|---|
| T1 konsept: cache-invalidering | **378 tok / 1 kall** | 9 370 / 4 | scantool **25×** |
| T2 konsept: token-utløp | **955 / 1** | 1 101 / 1 | ~uavgjort |
| T3 struktur: indikator-regler | **140 / 1** | 1 898 / 1 | scantool **14×** |
| T4 literal: grid-TTL | 4 144 / 3 | **3 068 / 4** | grep 1,4× |
| T5 oversikt: backend-arkitektur | 4 466 / 1 | **2 763 / 2** | grep 1,6× |
| **Sum** | **10 083 / 7** | 18 200 / 12 | scantool 1,8× |

## Tolkninger

1. **Vollgraven er nøyaktig der den ble predikert**: spissede konsept- og
   struktursøk («hvor invalideres cachen», «hvilke regeltyper finnes») —
   14–25× færre tokens, fordi treffene leveres med omsluttende funksjon,
   signatur og range i ett kall, mens grep-agenten må åpne filer for å få
   konteksten.
2. **Grep vinner literal-oppslag** (T4, som designet — troverdighetstesten
   besto) og denne oversiktsoppgaven (T5): `cat README + main.py` er
   billig når fasiten bor i toppfilene. Preview leverer kvalitativt mer
   (centrality, helse, git-aktivitet), men T5-fasiten krevde det ikke.
3. **Kall teller også**: 7 vs 12 kall = færre turer, lavere latens og
   mindre kontekstfragmentering — ikke priset inn i token-tallene.

## Ærlige begrensninger

- **Skriptede strategier, ikke ekte agenter** — dette måler
  informasjonslevering (nødvendig, ikke tilstrekkelig). M2b = ekte
  agent-episoder med samme oppgaver.
- Baseline er bevisst generøs (±40-linjers vinduer rundt treffklynger,
  topp-3 filer): første versjon med topp-2 feilet T4 fordi svaret bodde i
  filen med færrest treff — realistisk grep-smerte, men vi ga baseline
  fordelen.
- Substring-fasit kan i prinsippet treffes tilfeldig; faktaene er valgt
  distinkte.
- Ett repo, fem oppgaver. v1.0-porten krever samme margin på repoer vi
  ikke har tunet mot, med flere oppgaver per kategori.

## Neste (M2b/M2c)

- Flere repoer (klon ukjente åpne prosjekter) og 3–5 oppgaver per kategori
- Ekte agent-episoder: samme oppgaver, agent med kun baseline-verktøy vs
  kun scantool, mål tokens-til-korrekt-svar og svar-kvalitet
- T5-funnet er et produktsignal: preview bør ha en billigere default-modus
  eller bedre token-disiplin i seksjonene
