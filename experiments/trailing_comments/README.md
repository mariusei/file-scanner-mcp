# Trailing-kommentarer i Python-skjeletter (sg-T4-nyansen)

## Bakgrunn

M2b sg-T4: skjelettet viste `if tile_type == 'grid': return None` og
agentene måtte gjette hva TTL=None betyr («cacher evig» vs «cacher
ikke»). Kilden bar svaret tre steder: foranstående kommentarlinje
(`# Grid structure never changes`), trailing kommentar på den beholdte
linjen (`return None  # Never expires`), og docstring-linje 2.

Generisk skjelett (`_skeleton_lines`) beholder rå linjer og dermed
trailing-kommentarer allerede. Pythons AST-baserte kondensering
(`_skeleton_stmts`) mister dem — ast.unparse har ingen kommentarer.

## Hypotese

Å gjenfeste trailing-kommentarer på beholdte skjelettlinjer (via
tokenize, kun kommentarer med kode foran på samme linje) disambiguerer
verdi-bærende linjer til lav tokenkostnad.

## Preregistrerte beslutningsregler (skrevet FØR målingen)

Målt på alle .py-filer i scantool/src og internal-backend/backend/app
(ekte, utunet kode — sg-T4-kilden):

1. **Integrér** hvis total skjelett-tokenøkning < 3 % på repo-nivå OG
   dekningen er reell (> 0 berørte linjer i begge repo) OG
   sg-T4-linjen (`return None  # Never expires`) faktisk fanges.
2. **Vurder manuelt** ved økning 3–5 % (se på hva kommentarene faktisk
   sier — stalehet/støy teller mot).
3. **Ikke integrér** ved økning > 5 %, eller hvis dekningen er ~0
   (null-funn er et gyldig utfall: da var sg-T4 et enkelttilfelle).

Foranstående kommentarlinjer (full-linje) holdes UTENFOR — de er målt
bort tidligere i kondenseringsdesignet (test_keeps_control_flow_and_calls
asserterer at de droppes) og har høyere støyrisiko. Kun trailing.

## Måling (2026-06-11)

A/B per funksjon/metode: `_skeleton_stmts(body, 0, None)` vs
`_skeleton_stmts(body, 0, _trailing_comments(source))`, tokens via
`scanner._estimate_tokens`.

| Repo | funksjoner | berørte funksjoner | berørte linjer | skjelett-tokens |
|---|---|---|---|---|
| scantool/src | 724 | 38 | 62 | 92 165 → 92 555 (**+0,42 %**) |
| internal-backend/backend/app | 156 | 31 | 41 | 28 881 → 29 149 (**+0,93 %**) |

sg-T4-linjen fanges eksakt — alle grener i `get_tile_cache_ttl`
disambigueres:

```
if tile_type == 'grid':
 return None  # Never expires
elif tile_type == 'dataset':
 return 2592000  # 30 days (was 1 day) - data doesn't change
...
else:
 return 300  # 5 minutes default
```

Eksempler på fanget innhold (begge repo): verdi-forklaringer av typen
`# seconds to days`, `# 10GB in bytes`, `# Top 25% newest` — nettopp
disambiguering, ikke prosa-støy.

## Beslutning

Regel 1 innfridd (< 3 % på begge repo, reell dekning, sg-T4 dekket):
**INTEGRERT** i `PythonLanguage`-kondenseringen
(`_trailing_comments` + `emit(text, row)` i `_skeleton_stmts`).
Generisk skjelett (`_skeleton_lines` i basen) beholder rå linjer og
hadde egenskapen fra før. Golden-testene forble grønne — basic.py har
ingen trailing-kommentarer på beholdte linjer, så default-overflaten
driftet ikke.

Foranstående kommentarlinjer forblir utenfor (preregistrert avgrensning);
docstring-linje-2-sporet (sg-T4s tredje bærer) er ikke vurdert her.
