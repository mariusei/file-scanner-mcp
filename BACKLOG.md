# Backlog mot v1.0.0

Status per 2026-06-11. Frontier-arbeidet er levert (kondensering,
node-direkte saliency, git-signaler, helse, budsjett, delta, scan_diff,
innholdssøk med spor, moduser, benchmark M2/M2c/M2b). Dette dokumentet
gjør gjenstående arbeid actionable: hva, hvorfor (bevis), akseptkriterium.

## v1.0-porten (definisjonen)

v1.0.0 settes når: (1) output-kontrakten er frosset med golden-tester,
(2) benchmark-marginen holder på repoer vi ikke har tunet mot —
**omformulert etter M2b**: marginen som skal holde er SVARKVALITET
(fakta-dekning i ekte agent-episoder, målt 88 % vs 73 %), med
token-paritet eller bedre under budsjettpress. Bevis: harness 6/6 vs 5/6
(experiments/benchmark/README.md), M2b (experiments/benchmark/M2B.md).

## M1-kø (vedlikehold, prioritert)

1. ~~**Konsum-styring for agenter**~~ **LEVERT 2026-06-11**:
   kostnadstransparente verktøybeskrivelser i server.py; akseptkriteriet
   innfridd — token-gap 2,8× → 1,2× med kvalitet 86 % vs grep 67 %
   (M2B.md addendum). Restnyanse: åpne arkitekturspørsmål taper litt på
   økonomisering (sg-T5) — vurder oppgavebetinget styring senere.

2. ~~**Dogfooding-refaktor**~~ **LEVERT 2026-06-11**: 36 metodekopier
   fjernet i 16 språkplugins (−548/+56 linjer); BaseLanguage fikk
   defaults med kroker (_extract_definitions_regex,
   _extract_calls_tree_sitter/_regex, _handle_import, _get_ancestors).
   Akseptkriteriet innfridd: CODE HEALTH på src/scantool viser null
   duplikat-grupper — inkludert _extract_keyframes (css/scss) som lå
   skjult bak visningstaket på 5 grupper; 877/877 tester grønne.
   Reelle overstyringer bevart: swift (_structures_to_definitions_swift),
   java (is_cross_file-merking), rust («use statements»),
   sql/scss/generic/config (egen logikk).

3. ~~**Golden-output-tester / formatkontrakt**~~ **LEVERT 2026-06-11**:
   19 snapshots (18 språk via scan_file + dedikert fixture-katalog for
   scan_directory) i tests/golden/, håndhevet av tests/test_golden.py;
   oppdatering kun via `UPDATE_GOLDEN=1`. Frosset lag:
   scanner+formatter med defaults — file-info utelatt (mtime følger
   checkout), git-signaler/delta ligger i server-laget og er utenfor.
   Determinisme målt: 19/19 byte-identiske ved gjentatt kjøring, 19/19
   grønne i kopi uten .git med ferske mtimes. Kontrakten dokumentert i
   README («Output Contract»). **Sekvensvalg mot punkt 4**: frosset nå;
   punkt 4 går gjennom kontraktens egen mekanisme (bevisst endring →
   bevisst snapshot-oppdatering).

4. ~~**Docstring-tiering + parameterkonsistens**~~ **LEVERT 2026-06-11**:
   alle 7 verktøy i server.py følger samme tier-mal i Args
   (Common → Cost & slicing → Semantics & display; tomme tier utelates).
   mode lagt til scan_directory (server + FileScanner.scan_directory,
   default "balanced") med regresjonstest for propagering; scan_file
   sin udokumenterte mode-param fikk Args-linje. Akseptkriteriet
   innfridd via kontrakten: golden-testene forble grønne (default-output
   uendret), 895/895 totalt.

5. ~~**Småplukk**~~ **LEVERT 2026-06-11** (tre delpunkter, hver med måling):
   - *Størrelsesgate for flere språk*: **FALSIFISERT** — tree-sitter er
     raskere enn regex-fallbacken på 2 MB for java/ts/swift/sql (0,1–0,3x);
     Pythons 144x-avvik var kvadratisk `_get_ancestors` (DFS fra rot per
     node), omskrevet til parent-kjede: 284 s → 0,4 s på 2 MB (660x).
     Markdown-gaten bekreftet (2,8x) og beholdt. Se experiments/size_gate/.
   - *Swift-skjelettstøy*: `init_declaration` m.fl. gjenkjennes nå i
     `_SIGNIFICANT_NODE` (constructor/destructor/init/deinit/subscript);
     flerlinje-init-headere beholdes hele i stedet for `…` + `) {`.
   - *sg-T4/glimt-kommentar*: trailing-kommentarer gjenfestes på beholdte
     linjer i Python-skjeletter (tokenize-basert; generisk skjelett hadde
     egenskapen fra før). Målt +0,42 %/+0,93 % tokens på scantool/internal-backend,
     sg-T4-linjen («return None  # Never expires») dekkes. Foranstående
     kommentarlinjer bevisst utenfor. Se experiments/trailing_comments/.
   Golden-testene forble grønne gjennom alle tre — defaultflatens
   eneste endringer er skjelettforbedringene selv. Suite: 897.

## Åpne forskningsspor (post-1.0)

- M2c: flere SWE-bench-instanser (django/sympy for skala), flere kjøringer
  per celle, inter-rater-gradering
- Per-node churn inn i directory-vekting (krever billigere blame-strategi)
- Delta-modus på tvers av prosesser (persistert minne med samtykke)

## Bevisarkivet

- experiments/condensation/ — skjelett-/kondenseringsmålingene
- experiments/entropy_metrics/ — metrikk-, arkitektur-, dybde-, dedup- og
  glimt-eksperimentene med alle null-funn
- experiments/benchmark/ — harness, SWE-bench-suite, M2b med rålogger
- Commit-historikken b703458..HEAD — hver endring bærer sin måling
