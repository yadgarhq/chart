{{/*
THE PARENT'S OWN REFUSALS, AND THE ONLY THING THIS CHART EVER EVALUATES.

ADR-0777 is the record for this file and for `validate.yaml` beside it. Read that
first: it rules that the parent renders NO OBJECT of its own and carries exactly
ONE values-validating template, which emits nothing.

WHY A PARTIAL AND A CALLER, RATHER THAN ONE FILE. helm never renders a file whose
name begins with `_`, so a `fail` that lived only here would never execute — a
partial defines a named template and runs when something includes it. The
definition is here; the CALL is in `validate.yaml`, which helm does render. Do not
tidy the two into one file, and do not move the call into `_no_objects_of_its_own.tpl`.

THE GUARD, AND WHY IT IS NOT `.Release.IsInstall`. That field is TRUE for
`helm template`, so it does not separate an install from a render and no
template-time discriminator between the two exists. An unconditional refusal here
fires on the render of an adopter who brings their own platform layer, which the
suite asserts as `MODULES_ONLY_VALUES` in `scripts/tests/test_parent_chart.py`.

SO THE GUARD KEYS ON THE `platform.*.create` TOGGLES: any one of them being true,
with `platform.enabled` not false (ADR-0807). ADR-0777 records the narrowing this
buys and the operator accepted it on 2026-09-22: an adopter who brings their own
platform layer — `platform.enabled` false, or every `create` false — is NOT
refused for an empty admin token.

THE DEFAULTS OPEN THE GUARD SINCE ADR-0803 STEP B6. `chart/values.yaml` now sets
every `create` true, so these refusals run on the DEFAULT path: an adopter who
empties `gateway.adminBootstrap.tokenSecret`, or renames one side of a minted
Secret, is refused at their first render with no other change. The defaults
themselves satisfy every refusal, and the suite asserts that they render.

THE TOGGLES ARE RANGED OVER, NEVER ENUMERATED. A literal list of the seven names
`platform` ships today goes stale in silence the day an eighth block arrives —
the new toggle would be true, this guard would not see it, and the refusals would
not run for the adopter who set it. Ranging asks the values for what is there:
every block under `platform` that is a map and carries `create: true`.
`platform.enabled` is a bool and falls out; `platform.preflight` carries `enabled`
rather than `create` and falls out too.

EVERY READ IS NIL-SAFE, THROUGH A `default` CHAIN AT EVERY LEVEL, and the case it
is written for is a real test rather than defensive habit.

IT IS A `default` CHAIN AND NOT `dig`, AND THAT IS FORCED. `dig` is typed
`map[string]interface{}` and helm hands a template a `chartutil.Values`, so
`dig "platform" dict .Values` fails on EVERY render, including the bare default
one, with `error calling dig: interface conversion`. ADR-0777 asks for `dig` OR an
equivalent default chain; this is the equivalent one.

THE CHAIN IS UNIFORM AT EVERY LEVEL, AND NIL-SAFETY ALONE DOES NOT NEED IT UNIFORM.
ONE missing key is tolerated — the lookup yields nil and nothing raises — but a
SECOND field access on that nil DOES raise, which is why
`.Values.gateway.adminBootstrap.tokenSecret` and
`$platform.bootstrap.adminToken.secretName` cannot be written directly. Both forms
were measured on 2026-09-24, on helm 3.18.4 and 4.3.0 alike: each aborts the render
with `nil pointer evaluating interface {}.<field>`.

WHAT RAISES IS AN UNBROKEN DOTTED CHAIN, NOT DEPTH, and that is the part this
comment used to leave a reader to guess at. A PARENTHESIS BREAKS THE CHAIN.
`((.Values.a).b).c` and `(.Values.a.b).c` both yield nil and raise nothing; so does
`((.Values.a).b).c.d`, because once the root of an access is a parenthesised
expression no number of further accesses raises. Every read here that goes more than
one level deep is parenthesised, so every one of them is already chain-broken —
measured by removing EVERY `default` from the four deep reads while KEEPING the
parentheses, where the guard still refuses correctly on all three overlays of
`test_the_refusals_are_nil_safe_with_every_subchart_removed`, on both helms.

SO THE `default`s COERCE THE VALUE, AND THEY ALSO CARRY THE PARENTHESES. Coercion
is what keeps `empty`, `eq` and `toString` predictable on an absent key. The break
is theirs too, and inseparably: `default dict .Values.gateway` cannot be written
without parentheses around it, so deleting the call deletes the break with it and
leaves `.Values.gateway.adminBootstrap.tokenSecret` behind — which raises. DO NOT
"SIMPLIFY" ONE AWAY. Applying the same `default` at every level rather than only at
the two that raise is what keeps the rule readable: a reader does not have to count
how deep a lookup is to know whether it is safe.

`test_the_refusals_are_nil_safe_with_every_subchart_removed` IS WHERE THIS IS HELD,
and what it catches is stated rather than assumed. It opens this guard over a tree
with no subchart values at all, which is the only render where every level is
genuinely empty. It REDDENS on the mutation a contributor would really make — a
`default` deleted together with its parentheses — and on a direct
`.Values.platform.bootstrap.create`, each measured, each caught by the `nil pointer`
assertion rather than by a changed refusal. It does NOT redden on the artificial
deletion that keeps the parentheses, because that one leaves the chain broken and
moves only the coercion.

`test_the_parent_declares_no_templates_of_its_own` strips `dependencies` from a
copy of `Chart.yaml` and renders, so `.Values.platform` is ABSENT: an unguarded
`.Values.platform.bootstrap.create` RAISES there rather than evaluating false.
`.Values.gateway` needs the same treatment for a different reason — it exists in
`chart/values.yaml`, and `.Values.gateway.adminBootstrap` does not.

THE REFUSALS ARE ACCUMULATED AND RAISED ONCE. `fail` aborts at the first call, so
three separate `fail`s would make refusals two and three unreachable from any
values file that also trips the first — and a refusal no red case can reach is a
refusal nobody has shown to work. Every violation is collected, then one `fail`
carries them all.

A `fail` HERE ABORTS THE WHOLE ESTATE'S RENDER, exit 1 with ZERO objects, which is
the point: the install does not half-happen.
*/}}
{{- define "yadgar.validate" -}}
{{- $platform := default dict .Values.platform -}}
{{- $refusals := list -}}

{{/*
ADR-0787, AND THE ONE REFUSAL IN THIS FILE THAT SITS OUTSIDE THE `$creating`
GUARD. ADR-0787 rules that `platform` MAY install the five third-party operators
— cert-manager, KEDA, mariadb-operator, Envoy Gateway and Argo CD — cluster-wide
behind `operators.create`, DEFAULT FALSE, in a release of its own. It is not a
path this parent chart offers, and this clause is what says so at render time
instead of letting an adopter find out half-way through an apply.

WHY A SINGLE RELEASE CANNOT DO BOTH. An operator's CRDs and the objects that need
them land in one apply, so a release that installs cert-manager and renders a
Certificate applies the Certificate against a CRD that does not exist yet. That is
the same failure `yadgarhq/platform`'s own mixed-release refusal names one level
down; this is the parent's half of it.

IT IS OUTSIDE THE `$creating` GUARD, AND THAT IS THE WHOLE POINT. The guard opens
only when some `platform.<name>.create` is true. `platform.operators.certManager.create`
true with `operators.create` absent leaves `$creating` EMPTY — `platform.operators`
is a map whose own `create` key is missing — so a refusal written inside the guard
would never run for the values file that most needs it. Measured on `main` before
this clause existed, helm 4.3.0:
`helm template yadgar chart/ --set platform.operators.certManager.create=true`
rendered exit 0 and 32 objects.

THE SUB-KEYS ARE SUFFICIENT ON THEIR OWN, WHICH IS WHY EACH ONE IS NAMED. Every
operator dependency in `platform` is declared
`condition: operators.<op>.create,operators.create`, and helm evaluates the FIRST
valid path and stops. So `operators.certManager.create: true` installs cert-manager
while `operators.create` is false. A refusal reading the top-level key alone is
therefore FALSE in that shape, and the hole is the one this comment opens with.

THE TOP-LEVEL KEY ALREADY REACHED A REFUSAL BEFORE THIS CLAUSE, BY ACCIDENT, and
that is recorded so nobody reads the top-level case as this clause's proof.
`platform.operators` is a map carrying `create: true`, so the `$creating` range
below picks it up and the admin-token and `platform.enabled` refusals fire on a
bare `--set platform.operators.create=true` — measured exit 1 on `main`. With
`platform.enabled` true and `gateway.adminBootstrap.tokenSecret` set, the same key
rendered exit 0 and 32 objects. THAT is the case this clause closes, and the test
sets both so the message it reads is unambiguously this clause's.

THE OVERLAP WITH `$creating` IS LEFT ALONE, DELIBERATELY. `platform.operators.create`
is not a toggle that renders a platform-layer object, so the admin-token refusal's
"this install renders the platform layer (platform.operators.create)" reads a little
wide when both fire. Excluding `operators` by name would be an enumeration in the
one block this file keeps free of them, and it would change a shipped refusal for a
render that aborts either way. The refusals are accumulated, so this one is in the
same message.

THE OPERATOR BLOCKS ARE RANGED OVER, NEVER ENUMERATED, for the reason the
`$creating` block below gives: a literal list goes stale in silence the day a sixth
operator arrives. Ranging also means the message names the key the ADOPTER wrote,
so it cannot name a key that does not exist.

THE FIVE NAMES ARE `certManager`, `keda`, `mariadbOperator`, `envoyGateway` and
`argoCd`, VERIFIED AGAINST `yadgarhq/platform` AT `origin/feat/operators-toggle-step1`
AND NOT AGAINST THE PIN. `platform` 0.1.8 — the version `Chart.yaml` pins today —
carries no `operators` key at all, so no gate here can read those names off the
vendored tarball the way `test_the_minted_iam_keys_name_is_the_literal_this_refusal_assumes`
reads the minted Secret name. A gate that tried would be red today. The names are
carried by the TEST rather than by this template, which ranges: the assertion
therefore reads `platform`'s list and not a copy of this file's.

A PRESENT NON-MAP `platform.operators` IS REFUSED RATHER THAN READ, and the type
is tested on the RAW value because testing it after a `default` covers only half
the shapes. `default` substitutes on an EMPTY value, so `default dict true` is
`true` and `default dict false` is `dict` — an arm reading `kindIs "map"` off the
COERCED value therefore sees `false`, `null`, `0`, `""` and `[]` as the key being
ABSENT and permits every one of them. Measured on helm 4.3.0, with
`platform.enabled` true and the admin token set so no other refusal fires: at the
commit that first carried this clause, `true`, `yes` and `[a]` refused while
`false`, `null`, `0`, `""` and `[]` rendered exit 0. `[]` permitting while `[a]`
refused is the incoherence that found it.

`false` IS THE LOAD-BEARING ROW, not `true`. It is what an adopter writes who read
"default false" and wanted to be explicit, and helm leaves a dependency ENABLED
when NO path of a multi-path `condition:` resolves — so a permitted
`platform.operators: false` turns the whole operator set on one layer down. It did
not ship a mixed release only because `platform`'s own guard then aborted with
`can't evaluate field create in type bool`, which is the stack trace this clause
exists to replace with a key name. Measured before the raw-value arm: that same
trace for `--set platform.operators=true`, and `--set platform.operators=yes` too.

THE PRESENCE TEST IS `hasKey` AND IT HAS TO BE. `kindOf` reports `invalid` for an
explicit `operators: null` and for no `operators` key at all, so nothing reading
the value alone can tell them apart — measured on helm 4.3.0: `hasKey` is true for
the first and false for the second. An explicit null is a key the adopter wrote,
so it is refused, and `invalid` is reported to them as `null`.

AND THAT NULL ARM REACHES LESS THAN IT READS, WHICH IS A PIN'S DOING RATHER THAN
THIS CLAUSE'S. Helm DELETES a key whose value is null when a chart in the tree
DECLARES that key, and it does not put the declared default back — so once
`platform` began shipping `operators.create: false` at 0.1.9, an adopter's
`platform.operators: null` is gone before any template runs and the `hasKey` above
reads FALSE. That is indistinguishable here from an adopter who never wrote the
key, which is every other adopter, so this clause going quiet on that one shape is
correct. `platform` 0.1.11 refuses it from the one place the information survives —
arm one of its own `templates/render-checks.yaml`, naming the key as DELETED — and
`test_the_parent_refuses_a_platform_operators_key_that_is_not_a_mapping` records
which chart answers which shape. The arm below is NOT dead: with no subchart
declaring the key nothing triggers the deletion, and over
`chart_without_its_dependencies` this clause refuses `operators: null` by name on
helm 3.20.2 and 4.3.0 alike, measured 2026-09-26.

DO NOT MAKE THIS "NIL-SAFE" BY WIDENING THE `default`. Applying `default dict` to
`platform`'s sibling guard was measured to convert a crash into a SILENT mixed
release — exit 0 and no refusal from either guard. Refuse a present non-map; never
coerce it and read it.

IT IS A REAL TYPO RATHER THAN A HYPOTHETICAL, and refusing it is not the same
choice the `$creating` block below makes. That block SKIPS a non-map, which is
right there: it is looking for blocks and a scalar is simply not one. Here the key
itself is the thing the parent does not offer, so a scalar under that name is an
adopter asking for the operators path in a shape no key can be read out of — and
what `platform` would do with a bool where it expects a mapping is NOT measurable
from here, because `platform` 0.1.8 has no `operators` key at all. The refusal
says what is wrong and claims nothing about that.
*/}}
{{- $operatorKeys := list -}}
{{- $operatorsShape := "" -}}
{{- if kindIs "map" $platform -}}
{{- if hasKey $platform "operators" -}}
{{- if not (kindIs "map" $platform.operators) -}}
{{- $operatorsShape = kindOf $platform.operators -}}
{{- if eq $operatorsShape "invalid" -}}
{{- $operatorsShape = "null" -}}
{{- end -}}
{{- end -}}
{{- end -}}
{{- end -}}
{{- if $operatorsShape -}}
{{- $refusals = append $refusals (printf (join "" (list
      "platform.operators is a %s rather than a mapping, so no operators key can be read out of it. "
      "This parent chart offers no operators path at all: ADR-0787 rules that `platform` installs "
      "cert-manager, KEDA, mariadb-operator, Envoy Gateway and Argo CD behind operators.create, "
      "default false, in a release of its own. Remove platform.operators from this values file."))
      $operatorsShape) -}}
{{- else -}}
{{- $operators := default dict $platform.operators -}}
{{- if kindIs "bool" $operators.create -}}
{{- if $operators.create -}}
{{- $operatorKeys = append $operatorKeys "platform.operators.create" -}}
{{- end -}}
{{- end -}}
{{- range $name, $block := $operators -}}
{{- if kindIs "map" $block -}}
{{- if kindIs "bool" $block.create -}}
{{- if $block.create -}}
{{- $operatorKeys = append $operatorKeys (printf "platform.operators.%s.create" $name) -}}
{{- end -}}
{{- else if not (kindIs "invalid" $block.create) -}}
{{- $refusals = append $refusals (printf (join "" (list
      "platform.operators.%s.create is a %s rather than a boolean, so this chart cannot read it as a "
      "toggle. helm compares a toggle against a bool, and a value of any other type aborts the whole "
      "render on an incompatible-types comparison where a key name is what you need. Write true or "
      "false unquoted, or remove the key."))
      $name (kindOf $block.create)) -}}
{{- end -}}
{{- end -}}
{{- end -}}
{{- end -}}
{{- if $operatorKeys -}}
{{- $operatorsAsked := join ", " $operatorKeys -}}
{{- $refusals = append $refusals (printf (join "" (list
      "%s asks this parent chart to install third-party operators, and the parent offers no such "
      "path. ADR-0787 rules that `platform` MAY install cert-manager, KEDA, mariadb-operator, Envoy "
      "Gateway and Argo CD cluster-wide behind operators.create, default false, in a RELEASE OF ITS "
      "OWN installed before this one. One release cannot do both: an operator's CRDs and the objects "
      "that need them land in a single apply, so the objects are applied against definitions that do "
      "not exist yet and the install fails half-way. Set %s false here, and install the operators "
      "from `platform` on its own."))
      $operatorsAsked $operatorsAsked) -}}
{{- end -}}

{{/*
Every `platform.<name>.create` that is true, by name, in key order.

THE TYPE ARM IS HERE AND NOT ONLY IN THE OPERATORS CLAUSE ABOVE, because the
refusals are ACCUMULATED and the one `fail` runs last: a `platform.operators.create`
the clause above declined to read still reaches this range, and
`eq (default false $block.create) true` aborts the render on it before that `fail`
is ever reached. Measured on helm 4.3.0 — `platform.operators.create: 1` raised
`incompatible types for comparison: float64 and bool` at this line, both on `main`
and at the commit that first carried the operators clause. Refusing here names the
key for every `platform.<name>.create`, the operators one included, and names it
exactly once.

`default false` IS NIL-SAFE AND NEVER TYPE-SAFE. It substitutes on an EMPTY value,
so it turns an absent key into `false` and hands a present `"true"` or `1` straight
to `eq`.

A PRESENT NIL `create` USED TO BE LEFT ALONE HERE, ON A REASON THAT IS FALSE FOR
THE TWO BLOCKS THAT MATTER. The argument was that a nil never raised — `default
false nil` is `false`, that comparison is legal — so it could be read as false
"exactly as before". It is read as false HERE. Helm's dependency resolver does not
read it as false at all: `platform` declares `nats` under `condition: nats.create`,
and helm leaves a dependency ENABLED when the path its condition names does not
resolve. MEASURED 2026-09-26 against `platform` 0.1.12 on helm 3.20.2 and 4.3.0
alike: `platform.nats.create:` with nothing after it rendered EXIT 0 with 37
objects against the 32 of the bare default, the broker's five documents among them
and its `nats-ingress` NetworkPolicy NOT among them — the broker installed, with
nothing in front of it, out of a key this clause had just read as false.

SO ANY PRESENT `create` THAT IS NOT A BOOL IS REFUSED, AND `invalid` IS REPORTED AS
`null`. `hasKey` is what separates a present nil from an ABSENT key, because
`kindOf` answers `invalid` to both and cannot tell them apart (ADR-0794) — and an
absent `create` is what `cert-manager`, `keda`, `mariadb-operator`, `global` and
`preflight` all have in a default render, so refusing on the kind alone would
refuse every render in the estate.

IT IS REFUSED FOR EVERY BLOCK RATHER THAN FOR THE TWO DEPENDENCIES BY NAME, and
that is the ranging discipline this file already states rather than a widening
nobody asked for. Nothing in the VALUES says which `platform.<name>` blocks are
chart dependencies; `platform`'s own `Chart.yaml` does, and this chart does not
read it. An enumeration here would be a list to keep in step by attention, and the
day `platform` puts a sixth block behind a `condition:` the list would be wrong and
silent. For a block that is NOT a dependency the refusal costs an adopter a values
file that rendered nothing from a toggle they did write, which is not a
configuration anyone wants either.

`platform.operators.create` IS NOT REACHED BY THIS ARM AND DOES NOT NEED TO BE.
Helm DELETES that key when it is nulled, because `platform` declares it, so the
parent sees `hasKey` FALSE and cannot tell it from the adopter who never wrote it.
`platform` 0.1.12 refuses that one itself, from the one place the information
survives. `nats.create` nulls differently — the `nats` SUBCHART's own values are
coalesced into `platform.nats`, so the key comes back PRESENT and nil rather than
deleted — which is why this arm sees it and that one it does not.

A NIL OPERATOR SUB-KEY IS OUT OF SCOPE AND MEASURED SO. `platform.operators.
certManager.create:` with nothing after it rendered 32 objects at exit 0 on both
helm lines: the condition's FIRST path is unreadable, so helm falls through to
`operators.create` and the dependency is correctly off. The sub-key range below
therefore keeps its `invalid` exclusion, and the two ranges differ on purpose.
*/}}
{{- $creating := list -}}
{{- if kindIs "map" $platform -}}
{{- range $name, $block := $platform -}}
{{- if kindIs "map" $block -}}
{{- if kindIs "bool" $block.create -}}
{{- if $block.create -}}
{{- $creating = append $creating (printf "platform.%s.create" $name) -}}
{{- end -}}
{{- else if hasKey $block "create" -}}
{{- $wrote := kindOf $block.create -}}
{{- if eq $wrote "invalid" -}}{{- $wrote = "null" -}}{{- end -}}
{{- $refusals = append $refusals (printf (join "" (list
      "platform.%s.create is a %s rather than a boolean, so this chart cannot read it as a toggle. "
      "helm compares a toggle against a bool, and a value of any other type aborts the whole render "
      "on an incompatible-types comparison where a key name is what you need. A null is worse than "
      "an abort: `platform` declares nats under `condition: nats.create`, and helm leaves a "
      "dependency ENABLED when the path its condition names does not resolve — so a nulled toggle "
      "on a block that is a chart dependency installs it rather than leaving it out. Write true or "
      "false unquoted, or remove the key."))
      $name $wrote) -}}
{{- end -}}
{{- end -}}
{{- end -}}
{{- end -}}

{{/*
ADR-0807: `platform.enabled` FALSE TURNS THE WHOLE PLATFORM LAYER OFF, whatever the
`create` toggles say. `platform` is declared under `condition: platform.enabled`,
so helm leaves the subchart out and none of its objects render. The `create`
toggles are then inert, and the guard below is shut by emptying `$creating`: the
admin-token and `iam-keys` refusals are about Secrets the bootstrap Job mints, and
with the layer off it mints nothing.

ADR-0777's REFUSAL 3 IS RETIRED BY THE SAME RULING. It refused a `create` left true
with `platform.enabled` false, to catch an adopter who forgot `enabled: true`. The
defaults now set `enabled` true (ADR-0803 step B6), so it fired almost only on a
deliberate opt-out, which then took about ten keys. The opt-out is now two:
`platform.enabled: false` and `gateway.adminBootstrap.tokenSecret: ""`.

THE SECOND KEY IS DOCUMENTED, NOT REFUSED, and that is measured rather than
chosen. With the layer off nothing mints the admin token, and the gateway exits at
boot on a named Secret it cannot read — so a refusal naming a forgotten
`tokenSecret` clear looked right. It cannot be told apart from D80's all-off
render, which sets every `enabled` false and leaves that string alone: the refusal
failed `d80_portability.py`'s all-off pass, and this suite's copy of it, on
2026-09-27. ADR-0807 records the requirement in the README and the example.

ONLY A BOOL `false` IS "OFF". An absent or non-bool `platform.enabled` leaves the
dependency ENABLED in helm, and the shape refusal further down names it whatever
the `create` toggles say — it sits outside the guard for that reason.
*/}}
{{- $tokenSecret := default "" (default dict (default dict .Values.gateway).adminBootstrap).tokenSecret -}}
{{- if and (kindIs "bool" $platform.enabled) (not $platform.enabled) -}}
{{- $creating = list -}}
{{- end -}}

{{- if $creating -}}
{{- $asked := join ", " $creating -}}

{{/*
RULING 5. `gateway.adminBootstrap.tokenSecret` defaults EMPTY, which renders no
token file, no mount and no volume — the administrative bootstrap path disabled,
every other route serving, and the estate answering 503 to the one request that
creates the first user. An install of the whole estate with no admin token is an
estate nobody can create a user in, and the parent refuses it at render rather
than shipping it.
*/}}
{{- if empty $tokenSecret -}}
{{- $refusals = append $refusals (printf (join "" (list
      "gateway.adminBootstrap.tokenSecret is empty, and this install renders the platform layer (%s). "
      "An empty value renders no token file, no mount and no volume: the administrative bootstrap route "
      "is disabled and the estate answers 503 to the one request that creates the first administrator. "
      "Set gateway.adminBootstrap.tokenSecret to the name of the Secret the bootstrap Job mints."))
      $asked) -}}
{{- end -}}

{{/*
THE TWO NAMES ARE ONE NAME. The bootstrap Job MINTS a Secret under
`platform.bootstrap.adminToken.secretName`, and the gateway MOUNTS a Secret under
`gateway.adminBootstrap.tokenSecret`. Two values that disagree is an install in
which the token exists and nothing reads it, and the symptom is the same 503 the
refusal above is about — reached by a different route, which is why it is its own
refusal rather than a clause of that one.
*/}}
{{- $bootstrap := default dict $platform.bootstrap -}}
{{- if eq (default false $bootstrap.create) true -}}
{{- $minted := default "" (default dict $bootstrap.adminToken).secretName -}}
{{- if ne (toString $minted) (toString $tokenSecret) -}}
{{- $refusals = append $refusals (printf (join "" (list
      "platform.bootstrap.adminToken.secretName is %q and gateway.adminBootstrap.tokenSecret is %q, "
      "and platform.bootstrap.create is true. The bootstrap Job mints the first name and the gateway "
      "mounts the second, so two different names leave the token minted and unread. Set the two keys "
      "to one value."))
      (toString $minted) (toString $tokenSecret)) -}}
{{- end -}}

{{/*
THE SAME SHAPE FOR `iam-keys`, AND THE ONE DIFFERENCE IS THAT ONLY ONE SIDE IS A
KEY. `platform.bootstrap.iamKeys.create` mints a Secret whose name is a LITERAL
in the Job's script — `mint iam-keys 32` and `create iam-keys`, with
`"metadata":{"name":"iam-keys"}` in the body it POSTs. `iam` mounts its keys under
`iam.keysSecret`, which IS a value and defaults to that same name. So an adopter
who renames the value while the toggle is on gets a Job minting one name and a
Deployment mounting another, and the volume is NOT optional: the pod sticks in
`ContainerCreating` on a Secret nothing ever created. Measured 2026-09-25 on helm
3.18.4 and 4.3.0 alike, before this clause existed: `example/values.yaml` plus
`iam.keysSecret: my-own-iam-keys` rendered exit 0 and 81 objects, the Job carrying
`"metadata":{"name":"iam-keys"}` and the `iam` Deployment `secretName:
my-own-iam-keys`.

IT IS NESTED UNDER `bootstrap.create` BECAUSE THE JOB IS. `platform`'s
`templates/bootstrap-secrets.yaml` opens `{{ if .Values.bootstrap.create }}` at
the top of the file and `{{ if $bootstrap.iamKeys.create }}` inside it, so
`iamKeys.create` true with `bootstrap.create` false mints NOTHING. Keyed on
`iamKeys.create` alone this would refuse a configuration that is not broken.

THE COMPARISON IS EXACT, NOT A PREFIX AND NOT A SUBSTRING, and the distinction is
load-bearing rather than pedantic: `my-own-iam-keys` and `iam-keys-2` both CONTAIN
`iam-keys` and both name a Secret the Job never mints.
`test_the_parent_refuses_a_renamed_iam_keys_secret` builds the superset case as
well as the disjoint one, so an implementation that matched loosely would go red.

THIS CLAUSE ASSUMES THE MINTED NAME IS A LITERAL, AND THAT MUST BE REVISITED IF IT
STOPS BEING ONE. `platform.bootstrap.iamKeys` carries `create` and nothing else
today — verified at `platform` 0.1.8, where that chart's own `values.yaml` argues
the omission under "WHY THE THREE NAMES ARE NOT KEYS HERE". Should `platform` ever
gain a key for the minted name, an adopter could rename BOTH sides coherently, and
a refusal keyed only on `iam.keysSecret` would then fire on a correct setup: the
comparison has to become minted-versus-mounted, like the admin token's above.
`test_the_minted_iam_keys_name_is_the_literal_this_refusal_assumes` reads the
rendered Job and reddens if the minted name stops being this literal.
*/}}
{{- if eq (default false (default dict $bootstrap.iamKeys).create) true -}}
{{- $keysSecret := default "" (default dict .Values.iam).keysSecret -}}
{{- if ne (toString $keysSecret) "iam-keys" -}}
{{- $refusals = append $refusals (printf (join "" (list
      "platform.bootstrap.iamKeys.create is true, so the bootstrap Job mints a Secret named exactly "
      "iam-keys, and iam.keysSecret is %q. The Job mints the first name and the iam Deployment mounts "
      "the second as a volume that is not optional, so two different names leave the keys minted, "
      "unread, and the iam pod stuck in ContainerCreating on a Secret nothing created. Set "
      "iam.keysSecret to iam-keys, or set platform.bootstrap.iamKeys.create false and bring the "
      "Secret yourself."))
      (toString $keysSecret)) -}}
{{- end -}}
{{- end -}}
{{- end -}}

{{/*
A `platform.enabled` HELM CANNOT READ, refused by name. ADR-0777's refusal 3 used
to sit here too — a `create` left true with `platform.enabled` false — and ADR-0807
retired it: `false` now turns the whole layer off, and the block above shuts this
guard for it. What remains is the state helm gets WRONG.

`platform` is declared under `condition: platform.enabled`, and helm leaves a
dependency ENABLED when the path its condition names does not resolve. Measured
2026-09-26 on helm 3.20.2 and 4.3.0 alike, with this clause's own `fail` neutered
so the render could be counted:

  platform.enabled: false, platform.valkey.create: true  -> 32 objects, 0 valkey documents
  platform.enabled: <null>, the same toggle              -> 35 objects, 2 valkey documents

So a null is the platform layer GOING IN out of a key the values file never said
to install. The only thing helm says about it is `Condition path
'platform.enabled' for chart platform returned non-bool value`, on stderr, beside
whatever else is being printed.

AND THE STRING SHAPES DID NOT REACH A MESSAGE AT ALL. `ne` compares a string to a
bool by raising: measured at the same time, `platform.enabled: "yes"` aborted with
`error calling ne: incompatible types for comparison: string and bool` at this
line — a stack trace where ADR-0794 requires a key name. Testing the KIND before
comparing is what removes that, and it is the same `kindIs "bool"` discipline the
`create` toggles above now use.

`enabled: yes` UNQUOTED IS A YAML 1.1 BOOL AND STAYS GREEN, measured: 35 objects,
exit 0, no refusal. Only the quoted form is a string.

NO `hasKey` IS NEEDED HERE, unlike the `create` arm above, and the difference is
worth stating because the two look like they should match. An ABSENT
`platform.enabled` and a present non-bool one both leave helm unable to resolve
the condition, so both belong in the same message — there is nothing for `hasKey`
to separate. Above, an absent `create` is the DEFAULT STATE of five blocks and had
to be told apart from a nulled one.
*/}}
{{- end -}}

{{/*
THE SHAPE REFUSAL SITS OUTSIDE THE `$creating` GUARD, AND IT USED TO SIT INSIDE IT.
Inside, it waited for a `create` toggle to open the guard, and a `platform.enabled`
helm cannot read needs none: helm leaves the dependency enabled whatever the
toggles say, and `platform`'s preflight Job renders on its own. Measured
2026-09-27 on helm 3.18.4 and 4.3.0: `platform.enabled:` null with all seven
`create` false rendered exit 0, no refusal, and four `platform` objects — the
preflight Job, its ServiceAccount, Role and RoleBinding. The toggles that asked,
if any, are still named.

D80's all-off pass is unaffected: it writes `platform.enabled` as a bool false.
*/}}
{{- if not (kindIs "bool" $platform.enabled) -}}
{{- $enabledShape := kindOf $platform.enabled -}}
{{- if eq $enabledShape "invalid" -}}{{- $enabledShape = "null" -}}{{- end -}}
{{- $askedBy := "" -}}
{{- if $creating -}}{{- $askedBy = printf ", and %s asks for the platform layer" (join ", " $creating) -}}{{- end -}}
{{- $refusals = append $refusals (printf (join "" (list
      "platform.enabled is a %s rather than true or false%s. "
      "`platform` is declared under `condition: platform.enabled`, and helm leaves a dependency "
      "ENABLED when the path its condition names does not resolve — so this does NOT leave the "
      "platform layer out, it installs it out of a key that says nothing, and the only warning is a "
      "`returned non-bool value` line on stderr. Write platform.enabled true or false unquoted."))
      $enabledShape $askedBy) -}}
{{- end -}}

{{/*
B-U6, PART 1 (ledger 925/770): EVERY CLIENT SECRET A MODULE NAMES MUST BE A KEY
OF `platform.certificates.leaves`.

FIVE KEYS NAME A CLIENT SECRET TODAY, VERIFIED AGAINST EACH CHART'S OWN
VALUES AND SCHEMA RATHER THAN ASSUMED: `gateway.clientCertificate.secret`
(one leaf shared across gateway's three upstream dials — iam, task and
project, each gated by that dial's own `tls.enabled`), `iam.iamDb.tls.clientCertSecret`,
`task.taskDb.tls.clientCertSecret` and `project.projectDb.tls.clientCertSecret`
— measured at the pinned `gateway` 0.10.2, `iam` 0.10.0, `task` 0.7.0 and
`project` 0.3.0. Each is the Secret a caller mounts to PRESENT its own client
certificate, the opposite direction from `<dial>.tls.caSecret`, which VERIFIES
the server and is a different key this clause says nothing about.

A FIFTH KEY NOW JOINS THEM (ADR-0885): `iam.nats.tls.clientCertSecret`, iam's
own client leaf for the broker hop — measured at the pinned `iam` 0.11.0
schema, `nats.tls` now declares `clientCertSecret` alongside `enabled` and
`caSecret`. `gateway`'s NATS and valkey hops present no SEPARATE key: measured
at the pinned `gateway` 0.12.0, `nats.tls` and `valkey.tls` each still declare
only `enabled`/`caSecret`, and `templates/deployment.yaml` mounts the SAME
`clientCertificate.secret` already in `$clientSecrets` below for every one of
gateway's five dials (`$presentsIdentity`). So gateway's NATS/valkey hops are
already covered by the `gateway.clientCertificate.secret` entry; only iam's
new key is added here.

THE OPPOSITE-DIRECTION `<dial>.tls.caSecret` KEYS NOW HAVE A NATS/VALKEY
CROSS-CHECK TOO, in `$upstreamCaSecrets` gathered beside `$clientCaSecrets`
below: `gateway.nats.tls.caSecret`, `gateway.valkey.tls.caSecret` and
`iam.nats.tls.caSecret` are each the bundle a CLIENT verifies the broker or
the cache against, not a server verifying a caller — a different clause from
the one `$clientCaSecrets` gathers, but the same underlying invariant: every
leaf's Secret carries the issuing CA's `ca.crt`, so the name must still be a
key of `platform.certificates.leaves` — WHEN `platform` RUNS THAT BROKER OR
CACHE AT ALL (`.runs`, at the gather site below): a bring-your-own broker or
cache names its own, different CA on purpose, and this clause has nothing to
say about it. The gRPC dials' own `<dial>.tls.caSecret` keys (`iamDb.tls.caSecret`
and so on) remain outside every clause here.

SKIPPED WHEN `platform` IS NOT A KEY OF `.Subcharts` — `platform.enabled:
false`, or helm would not have resolved the dependency, so `leaves` does not
exist to check against (gate [I]; measured 2026-10-08 on helm 3.18.4 and
4.3.0: `(default dict (default dict .Subcharts.platform).Values).enabled` raises `nil pointer evaluating
interface {}.Values` once `platform.enabled` is false and the pin carries
`chart/ci/values.yaml`'s twelve switches). SKIPPED AGAIN WHEN
`platform.certificates.create` is not exactly `true`, for the reason
`certificates.yaml` itself skips: an adopter running their own CA mints these
Secrets under a name this chart never sees.

A SECRET NAME LEFT EMPTY IS NOT CHECKED. Four of the five keys default to
`""`, meaning "present no client certificate on this hop" — a valid
configuration this clause has nothing to say about; `iam.nats.tls.clientCertSecret`
is the exception, DEFAULT NON-EMPTY (`iam-client-tls`, ADR-0885) because iam
already held that leaf for a different mount before this key existed. Only
a NAMED secret is
checked against the leaf map, and the comparison is exact: `hasKey`, never a
prefix or a substring, for the reason `test_the_parent_refuses_a_renamed_iam_keys_secret`
already states for the admin-token pair above.
*/}}
{{- if hasKey .Subcharts "platform" -}}
{{- $platformValues := (default dict .Subcharts.platform).Values -}}

{{/*
B-U6, PART 1b (ruling R7, coordinator update 2026-10-08): THE SIX SERVERS' OWN
`tls.clientCaSecret` — the bundle each verifies a CALLER against — gets the
same "is a key of platform.certificates.leaves" check, now that all six B-U5
contracts are merged and the key renders (B-U5E convention item 4).

A LEAF'S SECRET CARRIES THE ISSUING CA'S BUNDLE TOO, which is why any leaf
name satisfies a `clientCaSecret`. cert-manager writes `ca.crt` — the full
certificate of the issuer that signed the leaf — into EVERY Certificate's
target Secret, not only `tls.crt`/`tls.key`; every leaf in this estate is
signed by the one internal CA (`platform.certificates.issuerRef`), so every
leaf's `ca.crt` is the SAME bundle. The convention of a server naming its OWN
serving leaf (`iam-db.tls.clientCaSecret: iam-db-tls`) is a locality
convention, not a requirement this clause enforces — any leaf key renders a
usable bundle.

`platform.internalCA.name` IS REFUSED BY NAME, EXPLICITLY, RATHER THAN LEFT TO
THE GENERIC "not a key of platform.certificates.leaves" CHECK BELOW. That
Secret is NOT a leaf — it is the CA's OWN Certificate, and cert-manager writes
the CA's PRIVATE KEY into it (`tls.key`), not only a public bundle. Mounting
it as a client-CA bundle hands the pod the authority to SIGN new certificates,
a materially different risk from a typo'd name, so it gets its own sentence
rather than sharing the generic one.

THIS CHECK SITS OUTSIDE `certificates.create`, DELIBERATELY (coordinator
review 2026-10-09): the danger is `platform.internalCA.create` minting that
Secret at all, which is independent of whether THIS chart also issues the
leaves under `certificates.leaves` — an adopter running `internalCA.create:
true` with `certificates.create: false` (their own CA, somebody else's
leaves) still must not point a `clientCaSecret` at the one Secret that holds
the CA's private key. The GENERIC not-a-leaf check, below, still needs
`certificates.leaves` to exist and stays inside that guard; this one does not
read `leaves` at all, so it does not need it.
*/}}
{{- $internalCaName := default "yadgar-internal-ca" (default dict $platformValues.internalCA).name -}}
{{- $clientCaSecrets := list -}}
{{- $iamClientCa := default "" (default dict (default dict (default dict .Subcharts.iam).Values).tls).clientCaSecret -}}
{{- if $iamClientCa -}}
{{- $clientCaSecrets = append $clientCaSecrets (dict "key" "iam.tls.clientCaSecret" "name" $iamClientCa) -}}
{{- end -}}
{{- $taskClientCa := default "" (default dict (default dict (default dict .Subcharts.task).Values).tls).clientCaSecret -}}
{{- if $taskClientCa -}}
{{- $clientCaSecrets = append $clientCaSecrets (dict "key" "task.tls.clientCaSecret" "name" $taskClientCa) -}}
{{- end -}}
{{- $projectClientCa := default "" (default dict (default dict (default dict .Subcharts.project).Values).tls).clientCaSecret -}}
{{- if $projectClientCa -}}
{{- $clientCaSecrets = append $clientCaSecrets (dict "key" "project.tls.clientCaSecret" "name" $projectClientCa) -}}
{{- end -}}
{{- $iamDbClientCa := default "" (default dict (default dict (default dict (index .Subcharts "iam-db")).Values).tls).clientCaSecret -}}
{{- if $iamDbClientCa -}}
{{- $clientCaSecrets = append $clientCaSecrets (dict "key" "iam-db.tls.clientCaSecret" "name" $iamDbClientCa) -}}
{{- end -}}
{{- $taskDbClientCa := default "" (default dict (default dict (default dict (index .Subcharts "task-db")).Values).tls).clientCaSecret -}}
{{- if $taskDbClientCa -}}
{{- $clientCaSecrets = append $clientCaSecrets (dict "key" "task-db.tls.clientCaSecret" "name" $taskDbClientCa) -}}
{{- end -}}
{{- $projectDbClientCa := default "" (default dict (default dict (default dict (index .Subcharts "project-db")).Values).tls).clientCaSecret -}}
{{- if $projectDbClientCa -}}
{{- $clientCaSecrets = append $clientCaSecrets (dict "key" "project-db.tls.clientCaSecret" "name" $projectDbClientCa) -}}
{{- end -}}
{{- range $clientCaSecrets -}}
{{- if eq .name $internalCaName -}}
{{- $refusals = append $refusals (printf (join "" (list
      "%s names %q, the Secret platform.internalCA mints for the CA ITSELF, which holds the CA's "
      "private key. Mounting it as a client-CA bundle would hand this pod the authority to sign "
      "new certificates, not just read one. Name a leaf's Secret instead: cert-manager writes the "
      "issuing CA's ca.crt into every Certificate's target Secret, so any key of "
      "platform.certificates.leaves carries the same bundle this one does."))
      .key .name) -}}
{{- end -}}
{{- end -}}

{{/*
THE OPPOSITE DIRECTION (ADR-0885): these three keys are the bundle a CLIENT
verifies the broker or the cache against, not a server verifying a caller,
so they are gathered separately from `$clientCaSecrets` rather than folded
into it — the two clauses share the invariant, not the direction, and
`$clientCaSecrets`'s own entries and message stay exactly as they were.
Gathered here, beside `$clientCaSecrets`, rather than inside the
`$certsCreate` guard below, for the same reason `platform.internalCA.name`'s
OWN check above sits outside it: the danger is `platform.internalCA.create`
minting that Secret at all, independent of whether this chart also issues
the leaves under `certificates.create`.

EACH ENTRY ALSO CARRIES `runs`, UNLIKE `$clientCaSecrets`'s six — the six
gRPC/-db servers are always module charts THIS parent deploys, but NATS and
valkey are not: `platform.nats.create`/`platform.valkey.create` (defaulted
`true` by THIS chart's own `values.yaml`, `false` by `platform`'s) toggle
whether `platform` runs the broker or the cache at all. An adopter who sets
either `false` brings their OWN broker or cache, with its OWN serving
certificate from a DIFFERENT CA — `gateway.nats.tls.caSecret` then correctly
names a Secret this chart's leaves never heard of, and the not-a-leaf check
below must stay silent on it (measured: `platform.nats.create: false` plus a
real external CA name there otherwise refused as a typo). The internal-CA
loop right below needs no such gate: `platform.internalCA.name`'s Secret is
dangerous whoever runs the broker.
*/}}
{{/*
`kindIs "bool"` GUARDS BOTH READS BEFORE ANY COMPARISON (the same convention
PART 3 below states for `clientAuth`): `platform.nats.create`/`valkey.create`
are not schema-typed, so a quoted "yes" reaching a bare `eq ... true` would
panic the WHOLE render with a raw Go type-mismatch error — aborting before
`platform`'s own named refusal for that malformed value is ever reached,
exactly the outcome `test_tag_wall.py`'s `THE_REGISTER_KEY_SHAPES` table
exists to catch (measured: it did, on the first version of this line).
*/}}
{{- $natsCreateRaw := default false (default dict $platformValues.nats).create -}}
{{- $natsRuns := and (kindIs "bool" $natsCreateRaw) $natsCreateRaw -}}
{{- $valkeyCreateRaw := default false (default dict $platformValues.valkey).create -}}
{{- $valkeyRuns := and (kindIs "bool" $valkeyCreateRaw) $valkeyCreateRaw -}}
{{- $upstreamCaSecrets := list -}}
{{- $gatewayNatsCa := default "" (default dict (default dict (default dict (default dict .Subcharts.gateway).Values).nats).tls).caSecret -}}
{{- if $gatewayNatsCa -}}
{{- $upstreamCaSecrets = append $upstreamCaSecrets (dict "key" "gateway.nats.tls.caSecret" "name" $gatewayNatsCa "verifies" "the broker" "runs" $natsRuns) -}}
{{- end -}}
{{- $gatewayValkeyCa := default "" (default dict (default dict (default dict (default dict .Subcharts.gateway).Values).valkey).tls).caSecret -}}
{{- if $gatewayValkeyCa -}}
{{- $upstreamCaSecrets = append $upstreamCaSecrets (dict "key" "gateway.valkey.tls.caSecret" "name" $gatewayValkeyCa "verifies" "the cache" "runs" $valkeyRuns) -}}
{{- end -}}
{{- $iamNatsCa := default "" (default dict (default dict (default dict (default dict .Subcharts.iam).Values).nats).tls).caSecret -}}
{{- if $iamNatsCa -}}
{{- $upstreamCaSecrets = append $upstreamCaSecrets (dict "key" "iam.nats.tls.caSecret" "name" $iamNatsCa "verifies" "the broker" "runs" $natsRuns) -}}
{{- end -}}
{{- range $upstreamCaSecrets -}}
{{- if eq .name $internalCaName -}}
{{- $refusals = append $refusals (printf (join "" (list
      "%s names %q, the Secret platform.internalCA mints for the CA ITSELF, which holds the CA's "
      "private key. Mounting it as the bundle that verifies %s would hand this pod the authority "
      "to sign new certificates, not just read one. Name a leaf's Secret instead: cert-manager "
      "writes the issuing CA's ca.crt into every Certificate's target Secret, so any key of "
      "platform.certificates.leaves carries the same bundle this one does."))
      .key .name .verifies) -}}
{{- end -}}
{{- end -}}

{{- $certsCreate := default false (default dict $platformValues.certificates).create -}}
{{- if eq $certsCreate true -}}
{{- $leaves := default dict (default dict $platformValues.certificates).leaves -}}
{{- $clientSecrets := list -}}
{{- $gatewayCallerSecret := default "" (default dict (default dict (default dict .Subcharts.gateway).Values).clientCertificate).secret -}}
{{- if $gatewayCallerSecret -}}
{{- $clientSecrets = append $clientSecrets (dict "key" "gateway.clientCertificate.secret" "name" $gatewayCallerSecret) -}}
{{- end -}}
{{- $iamCallerSecret := default "" (default dict (default dict (default dict (default dict .Subcharts.iam).Values).iamDb).tls).clientCertSecret -}}
{{- if $iamCallerSecret -}}
{{- $clientSecrets = append $clientSecrets (dict "key" "iam.iamDb.tls.clientCertSecret" "name" $iamCallerSecret) -}}
{{- end -}}
{{- $iamNatsCallerSecret := default "" (default dict (default dict (default dict (default dict .Subcharts.iam).Values).nats).tls).clientCertSecret -}}
{{- if $iamNatsCallerSecret -}}
{{- $clientSecrets = append $clientSecrets (dict "key" "iam.nats.tls.clientCertSecret" "name" $iamNatsCallerSecret) -}}
{{- end -}}
{{- $taskCallerSecret := default "" (default dict (default dict (default dict (default dict .Subcharts.task).Values).taskDb).tls).clientCertSecret -}}
{{- if $taskCallerSecret -}}
{{- $clientSecrets = append $clientSecrets (dict "key" "task.taskDb.tls.clientCertSecret" "name" $taskCallerSecret) -}}
{{- end -}}
{{- $projectCallerSecret := default "" (default dict (default dict (default dict (default dict .Subcharts.project).Values).projectDb).tls).clientCertSecret -}}
{{- if $projectCallerSecret -}}
{{- $clientSecrets = append $clientSecrets (dict "key" "project.projectDb.tls.clientCertSecret" "name" $projectCallerSecret) -}}
{{- end -}}
{{- range $clientSecrets -}}
{{- if not (hasKey $leaves .name) -}}
{{- $refusals = append $refusals (printf (join "" (list
      "%s names the Secret %q as the client certificate it presents, and %q is not a key of "
      "platform.certificates.leaves. The parent issues every client leaf this estate mounts under "
      "platform.certificates.leaves (ledger 925), so a name that is not one of its keys is a Secret "
      "cert-manager never creates: the pod mounting it sticks in ContainerCreating. Check the name "
      "against platform.certificates.leaves for a typo in %s."))
      .key .name .name .key) -}}
{{- end -}}
{{- end -}}

{{/*
THE GENERIC not-a-leaf CHECK FOR `clientCaSecret`, NOW REUSING `$clientCaSecrets`
GATHERED ABOVE. Every entry already matched against `$internalCaName`; an
entry that WAS that name already carries its own refusal and is skipped here
(`ne .name $internalCaName`) so a values file naming it gets one sentence,
not two.
*/}}
{{- range $clientCaSecrets -}}
{{- if and (ne .name $internalCaName) (not (hasKey $leaves .name)) -}}
{{- $refusals = append $refusals (printf (join "" (list
      "%s names the Secret %q as the bundle it verifies a caller against, and %q is not a key of "
      "platform.certificates.leaves. Every leaf's Secret carries the issuing CA's ca.crt, so any "
      "leaf name renders a usable bundle; a name that is not one of platform.certificates.leaves's "
      "keys is a Secret cert-manager never creates. Check the name against "
      "platform.certificates.leaves for a typo in %s."))
      .key .name .name .key) -}}
{{- end -}}
{{- end -}}

{{/*
THE SAME not-a-leaf CHECK FOR `$upstreamCaSecrets`, GATHERED ABOVE beside
`$clientCaSecrets`. Every entry already matched against `$internalCaName`;
an entry that WAS that name already carries its own refusal and is skipped
here (`ne .name $internalCaName`), the same convention as the loop above for
`$clientCaSecrets`. `.runs` IS THE DIFFERENCE FROM THAT LOOP: an entry whose
broker or cache `platform` does not run (`platform.nats.create`/`valkey.create`
false, bring-your-own) is skipped here too — its CA name is correctly NOT
one of this chart's leaves, and checking it anyway would refuse a correct
bring-your-own configuration, exactly what this suite's own convention (see
`test_the_parent_refuses_a_renamed_iam_keys_secret`) says is worse than no
check at all.
*/}}
{{- range $upstreamCaSecrets -}}
{{- if and .runs (ne .name $internalCaName) (not (hasKey $leaves .name)) -}}
{{- $refusals = append $refusals (printf (join "" (list
      "%s names the Secret %q as the bundle it verifies %s against, and %q is not a key of "
      "platform.certificates.leaves. Every leaf's Secret carries the issuing CA's ca.crt, so any "
      "leaf name renders a usable bundle; a name that is not one of platform.certificates.leaves's "
      "keys is a Secret cert-manager never creates. Check the name against "
      "platform.certificates.leaves for a typo in %s."))
      .key .name .verifies .name .key) -}}
{{- end -}}
{{- end -}}
{{- end -}}
{{- end -}}

{{/*
B-U6, PART 2 (ledger 925/770, M-reaudit-B RS-5, M-reaudit3-B): A SERVER MAY NOT
ENFORCE A HANDSHAKE ITS ONLY CALLER NEVER PRESENTS.

EACH OF THE SIX gRPC SERVERS HAS EXACTLY ONE CALLER IN THIS ESTATE, VERIFIED
AGAINST EACH CHART'S OWN DIAL CONFIG: `gateway` 0.10.2 dials `iam`, `task` and
`project` (one `clientCertificate` shared across all three, gated per-dial by
that dial's own `tls.enabled`); `iam` 0.10.0 dials `iam-db`; `task` 0.7.0 dials
`task-db`; `project` 0.3.0 dials `project-db`. A server whose `tls.clientAuth`
is `optional` or `required` while its one caller is not wired to present
anything is an install that looks protected and is not: the server VERIFIES a
certificate its caller never sends, which either refuses every call
(`required`) or quietly accepts none (`optional`).

"PRESENTS NOTHING" IS TWO INDEPENDENT WAYS TO FAIL, so both are checked. The
dial's own `tls.enabled` false means the hop runs in cleartext, so no
certificate of any kind crosses it. The dial's own `tls.enabled` true with its
client-certificate Secret left empty means the hop is encrypted but the
client leg presents no identity — the Secret that would carry it was never
named.

`kindIs "string"` GUARDS EVERY `clientAuth` READ BEFORE ANY COMPARISON
(B-U5E convention item 1): the server's own schema deliberately never types
this key (ruling R1, ADR-0847 — an `enum`/`type` would pre-empt the render
check's own named refusal for a bare, unquoted `off`), so a bare
`off`/`optional`/`required` read unquoted is a bool here and `has`/`eq`
against a bool rather than a string would abort the whole render on an
incompatible-types panic instead of reaching that server's own named
refusal first.

EACH SERVER'S OWN `clientAuth` RENDER CHECK USED TO REFUSE `optional` AND
`required` UNCONDITIONALLY, until its own B-U5 contract lifted that refusal
(B-U5E convention) — all six landed during this unit's own work (iam#95,
iam-db#86, task#74, task-db#87, project#30, project-db#56), and the parent's
pin was bumped to match before this file's test suite was finished. So
`test_parent_chart.py` exercises each of these six clauses against the real,
unmodified pin: `--set iam.tls.clientAuth=required` now reaches THIS
template, not `iam`'s own `templates/render-checks.yaml`, measured
2026-10-08. Each server's own contract ALSO now requires `tls.clientCaSecret`
whenever `clientAuth` is `optional`/`required` — a check of its OWN, about
which authority it verifies a caller against, not about whether a caller
presents one — so a red case for this clause names a real leaf there too, or
the server's own refusal fires first and names nothing this clause is about.
*/}}
{{- $iamTls := default dict (default dict (default dict .Subcharts.iam).Values).tls -}}
{{- if and (kindIs "string" $iamTls.clientAuth) (has $iamTls.clientAuth (list "optional" "required")) -}}
{{- $callerEnabled := default false (default dict (default dict (default dict (default dict .Subcharts.gateway).Values).iam).tls).enabled -}}
{{- $callerSecret := default "" (default dict (default dict (default dict .Subcharts.gateway).Values).clientCertificate).secret -}}
{{- if or (not $callerEnabled) (not $callerSecret) -}}
{{- $refusals = append $refusals (printf (join "" (list
      "iam.tls.clientAuth is %q, which verifies a client certificate on every call, and gateway — "
      "iam's only caller in this estate — presents none: gateway.iam.tls.enabled is %t and "
      "gateway.clientCertificate.secret is %q. Set gateway.iam.tls.enabled true and name "
      "gateway.clientCertificate.secret, or set iam.tls.clientAuth back to \"off\"."))
      $iamTls.clientAuth $callerEnabled $callerSecret) -}}
{{- end -}}
{{- end -}}

{{- $taskTls := default dict (default dict (default dict .Subcharts.task).Values).tls -}}
{{- if and (kindIs "string" $taskTls.clientAuth) (has $taskTls.clientAuth (list "optional" "required")) -}}
{{- $callerEnabled := default false (default dict (default dict (default dict (default dict .Subcharts.gateway).Values).task).tls).enabled -}}
{{- $callerSecret := default "" (default dict (default dict (default dict .Subcharts.gateway).Values).clientCertificate).secret -}}
{{- if or (not $callerEnabled) (not $callerSecret) -}}
{{- $refusals = append $refusals (printf (join "" (list
      "task.tls.clientAuth is %q, which verifies a client certificate on every call, and gateway — "
      "task's only caller in this estate — presents none: gateway.task.tls.enabled is %t and "
      "gateway.clientCertificate.secret is %q. Set gateway.task.tls.enabled true and name "
      "gateway.clientCertificate.secret, or set task.tls.clientAuth back to \"off\"."))
      $taskTls.clientAuth $callerEnabled $callerSecret) -}}
{{- end -}}
{{- end -}}

{{- $projectTls := default dict (default dict (default dict .Subcharts.project).Values).tls -}}
{{- if and (kindIs "string" $projectTls.clientAuth) (has $projectTls.clientAuth (list "optional" "required")) -}}
{{- $callerEnabled := default false (default dict (default dict (default dict (default dict .Subcharts.gateway).Values).project).tls).enabled -}}
{{- $callerSecret := default "" (default dict (default dict (default dict .Subcharts.gateway).Values).clientCertificate).secret -}}
{{- if or (not $callerEnabled) (not $callerSecret) -}}
{{- $refusals = append $refusals (printf (join "" (list
      "project.tls.clientAuth is %q, which verifies a client certificate on every call, and "
      "gateway — project's only caller in this estate — presents none: gateway.project.tls.enabled "
      "is %t and gateway.clientCertificate.secret is %q. Set gateway.project.tls.enabled true and "
      "name gateway.clientCertificate.secret, or set project.tls.clientAuth back to \"off\"."))
      $projectTls.clientAuth $callerEnabled $callerSecret) -}}
{{- end -}}
{{- end -}}

{{- $iamDbTls := default dict (default dict (default dict (index .Subcharts "iam-db")).Values).tls -}}
{{- if and (kindIs "string" $iamDbTls.clientAuth) (has $iamDbTls.clientAuth (list "optional" "required")) -}}
{{- $callerEnabled := default false (default dict (default dict (default dict (default dict .Subcharts.iam).Values).iamDb).tls).enabled -}}
{{- $callerSecret := default "" (default dict (default dict (default dict (default dict .Subcharts.iam).Values).iamDb).tls).clientCertSecret -}}
{{- if or (not $callerEnabled) (not $callerSecret) -}}
{{- $refusals = append $refusals (printf (join "" (list
      "iam-db.tls.clientAuth is %q, which verifies a client certificate on every call, and iam — "
      "iam-db's only caller in this estate — presents none: iam.iamDb.tls.enabled is %t and "
      "iam.iamDb.tls.clientCertSecret is %q. Set iam.iamDb.tls.enabled true and name "
      "iam.iamDb.tls.clientCertSecret, or set iam-db.tls.clientAuth back to \"off\"."))
      $iamDbTls.clientAuth $callerEnabled $callerSecret) -}}
{{- end -}}
{{- end -}}

{{- $taskDbTls := default dict (default dict (default dict (index .Subcharts "task-db")).Values).tls -}}
{{- if and (kindIs "string" $taskDbTls.clientAuth) (has $taskDbTls.clientAuth (list "optional" "required")) -}}
{{- $callerEnabled := default false (default dict (default dict (default dict (default dict .Subcharts.task).Values).taskDb).tls).enabled -}}
{{- $callerSecret := default "" (default dict (default dict (default dict (default dict .Subcharts.task).Values).taskDb).tls).clientCertSecret -}}
{{- if or (not $callerEnabled) (not $callerSecret) -}}
{{- $refusals = append $refusals (printf (join "" (list
      "task-db.tls.clientAuth is %q, which verifies a client certificate on every call, and task — "
      "task-db's only caller in this estate — presents none: task.taskDb.tls.enabled is %t and "
      "task.taskDb.tls.clientCertSecret is %q. Set task.taskDb.tls.enabled true and name "
      "task.taskDb.tls.clientCertSecret, or set task-db.tls.clientAuth back to \"off\"."))
      $taskDbTls.clientAuth $callerEnabled $callerSecret) -}}
{{- end -}}
{{- end -}}

{{- $projectDbTls := default dict (default dict (default dict (index .Subcharts "project-db")).Values).tls -}}
{{- if and (kindIs "string" $projectDbTls.clientAuth) (has $projectDbTls.clientAuth (list "optional" "required")) -}}
{{- $callerEnabled := default false (default dict (default dict (default dict (default dict .Subcharts.project).Values).projectDb).tls).enabled -}}
{{- $callerSecret := default "" (default dict (default dict (default dict (default dict .Subcharts.project).Values).projectDb).tls).clientCertSecret -}}
{{- if or (not $callerEnabled) (not $callerSecret) -}}
{{- $refusals = append $refusals (printf (join "" (list
      "project-db.tls.clientAuth is %q, which verifies a client certificate on every call, and "
      "project — project-db's only caller in this estate — presents none: "
      "project.projectDb.tls.enabled is %t and project.projectDb.tls.clientCertSecret is %q. Set "
      "project.projectDb.tls.enabled true and name project.projectDb.tls.clientCertSecret, or set "
      "project-db.tls.clientAuth back to \"off\"."))
      $projectDbTls.clientAuth $callerEnabled $callerSecret) -}}
{{- end -}}
{{- end -}}

{{/*
B-U6, PART 3 (ledger 925/770, M-reaudit-B RS-5, M-reaudit3-B): NATS AND VALKEY,
WHOSE `tls.clientAuth`, `tls.enabled` AND `tls.plaintext` ARE PLATFORM-OWNED
KEYS (B-L1, the folded B-N2/B-V2 expand) THE PARENT ALONE CAN CROSS-CHECK
AGAINST A CLIENT'S OWN DIAL FLAGS, which live in `gateway` and `iam` rather
than in `platform`.

NATS HAS NO OPTIONAL CLIENT-CERTIFICATE MODE (ADR-0854): its `verify` is
require-and-verify only, so its `clientAuth` set is `off | required` rather
than the three-way set every gRPC server and valkey carry — mirroring
`platform`'s own render check. `gateway` 0.10.2 and `iam` 0.10.0 are NATS's
only two clients in this estate (`iam` publishes cache-invalidation events;
`gateway` subscribes), each with its own `nats.tls.enabled`. `valkey`'s only
client in this estate is `gateway` (`gateway.valkey.tls.enabled`); no other
module dials it.

`allow_non_tls` IS A PASSTHROUGH TO THE UPSTREAM nats-server CONFIG, not a
`platform`-owned key the way `nats.tls.enabled`/`clientAuth` are — confirmed
against the plan (plan-final.md B-N2: "for the transport step only,
`nats.config.merge.allow_non_tls`") and against the pinned schema: `nats.tls`
is CLOSED (`additionalProperties: false`, only `enabled`/`clientAuth`), so
`platform.nats.tls.allowNonTls` is refused by `platform`'s own schema before
this template ever runs — measured 2026-10-09, `--set
platform.nats.tls.allowNonTls=true` exits 1 with `additional properties
'allowNonTls' not allowed`. `nats` itself (one level up) is OPEN, so
`nats.config.merge.allow_non_tls` reaches the broker's own config the same
way `nats.config.merge.authorization` already does for the two accounts
`platform`'s own `values.yaml` declares.

THE gRPC CLAUSES ABOVE LOST THIS GAP WHEN B-U5 LANDED; `platform` HAS NONE OF
IT, because B-N2 and B-V2 (platform 0.2.0, 0.2.1) now render and require
`nats.tls`/`valkey.tls` themselves: `platform/templates/render-checks.yaml`
refuses any posture its own contract disagrees with, UNCONDITIONALLY, before
this template ever runs. Each clause below cross-checks the posture
`platform` already accepted against its two clients, so it is never the
first refusal — exercised in the test suite against the real, pinned
`platform` chart directly, no vendored-line rewrite needed any more.
*/}}
{{- if hasKey .Subcharts "platform" -}}
{{- $platformTlsValues := (default dict .Subcharts.platform).Values -}}
{{- $natsTls := default dict (default dict $platformTlsValues.nats).tls -}}
{{- $valkeyTls := default dict (default dict $platformTlsValues.valkey).tls -}}

{{- if and (kindIs "string" $natsTls.clientAuth) (eq $natsTls.clientAuth "required") -}}
{{- $gatewayEnabled := default false (default dict (default dict (default dict (default dict .Subcharts.gateway).Values).nats).tls).enabled -}}
{{- $iamEnabled := default false (default dict (default dict (default dict (default dict .Subcharts.iam).Values).nats).tls).enabled -}}
{{/*
ADR-0885: "ENABLED" ALONE IS NOT "PRESENTS A CERTIFICATE" — the dial can run
over TLS and still mount no identity if its own leaf-secret key is empty, the
same gap B-U5's gRPC clauses closed above (`$callerSecret` beside
`$callerEnabled`). gateway presents the ONE shared `clientCertificate.secret`
on this hop too (no separate NATS key, per the comment at $clientSecrets
above); iam presents its own `nats.tls.clientCertSecret` (ADR-0885).
*/}}
{{- $gatewaySecret := default "" (default dict (default dict (default dict .Subcharts.gateway).Values).clientCertificate).secret -}}
{{- $iamSecret := default "" (default dict (default dict (default dict (default dict .Subcharts.iam).Values).nats).tls).clientCertSecret -}}
{{- if or (not $gatewayEnabled) (not $iamEnabled) (not $gatewaySecret) (not $iamSecret) -}}
{{- $refusals = append $refusals (printf (join "" (list
      "platform.nats.tls.clientAuth is \"required\", which verifies a client certificate on every "
      "connection, and NATS's only two clients in this estate present it like this: "
      "gateway.nats.tls.enabled is %t and gateway.clientCertificate.secret is %q; iam.nats.tls.enabled "
      "is %t and iam.nats.tls.clientCertSecret is %q. A client whose own nats.tls.enabled is false "
      "connects in cleartext and presents no certificate at all, and one whose secret is empty "
      "presents no identity even over an encrypted connection — either way the broker cannot verify "
      "it. Set both clients' nats.tls.enabled true and name both client-certificate secrets, or set "
      "platform.nats.tls.clientAuth back to \"off\"."))
      $gatewayEnabled $gatewaySecret $iamEnabled $iamSecret) -}}
{{- end -}}
{{- end -}}

{{- if and (kindIs "string" $valkeyTls.clientAuth) (has $valkeyTls.clientAuth (list "optional" "required")) -}}
{{- $gatewayEnabled := default false (default dict (default dict (default dict (default dict .Subcharts.gateway).Values).valkey).tls).enabled -}}
{{/*
ADR-0885: SAME GAP AS NATS ABOVE — gateway's valkey hop presents the same
shared `clientCertificate.secret`, which can be empty while `tls.enabled` is
true.
*/}}
{{- $gatewaySecret := default "" (default dict (default dict (default dict .Subcharts.gateway).Values).clientCertificate).secret -}}
{{- if or (not $gatewayEnabled) (not $gatewaySecret) -}}
{{- $refusals = append $refusals (printf (join "" (list
      "platform.valkey.tls.clientAuth is %q, which verifies a client certificate on every "
      "connection, and gateway — valkey's only client in this estate — presents it like this: "
      "gateway.valkey.tls.enabled is %t and gateway.clientCertificate.secret is %q. A client with "
      "tls.enabled false connects in cleartext and presents no certificate at all, and one with an "
      "empty secret presents no identity even over an encrypted connection — either way the cache "
      "cannot verify it. Set gateway.valkey.tls.enabled true and name "
      "gateway.clientCertificate.secret, or set platform.valkey.tls.clientAuth back to \"off\"."))
      $valkeyTls.clientAuth $gatewayEnabled $gatewaySecret) -}}
{{- end -}}
{{- end -}}

{{- if and (kindIs "bool" $valkeyTls.plaintext) (not $valkeyTls.plaintext) -}}
{{- $gatewayEnabled := default false (default dict (default dict (default dict (default dict .Subcharts.gateway).Values).valkey).tls).enabled -}}
{{- if not $gatewayEnabled -}}
{{- $refusals = append $refusals (printf (join "" (list
      "platform.valkey.tls.plaintext is false, so the cache accepts only TLS connections, and "
      "gateway.valkey.tls.enabled is false — valkey's only client in this estate dials in "
      "cleartext. The one connection this estate makes to valkey would be refused at the socket, "
      "not at the application. Set gateway.valkey.tls.enabled true, or set "
      "platform.valkey.tls.plaintext back to true."))) -}}
{{- end -}}
{{- end -}}

{{- if and (kindIs "bool" $natsTls.enabled) $natsTls.enabled -}}
{{- $allowNonTls := (default dict (default dict (default dict $platformTlsValues.nats).config).merge).allow_non_tls -}}
{{- if not (and (kindIs "bool" $allowNonTls) $allowNonTls) -}}
{{- $gatewayEnabled := default false (default dict (default dict (default dict (default dict .Subcharts.gateway).Values).nats).tls).enabled -}}
{{- $iamEnabled := default false (default dict (default dict (default dict (default dict .Subcharts.iam).Values).nats).tls).enabled -}}
{{- if or (not $gatewayEnabled) (not $iamEnabled) -}}
{{- $refusals = append $refusals (printf (join "" (list
      "platform.nats.tls.enabled is true and platform.nats.config.merge.allow_non_tls is not true, "
      "so the broker accepts only TLS connections, and gateway.nats.tls.enabled is %t and "
      "iam.nats.tls.enabled is %t — NATS's only two clients in this estate. A client whose own "
      "nats.tls.enabled is false dials in cleartext and the broker would refuse it at the socket. "
      "Set both clients' nats.tls.enabled true, or set platform.nats.config.merge.allow_non_tls "
      "true to let a plaintext client through the same port."))
      $gatewayEnabled $iamEnabled) -}}
{{- end -}}
{{- end -}}
{{- end -}}
{{- end -}}

{{/*
THE ONE `fail`, AND IT SITS OUTSIDE THE `$creating` GUARD SO THE ADR-0787 CLAUSE
AND THE `platform.enabled` SHAPE CLAUSE CAN REACH IT. Of the refusals ABOVE
`{{- if $creating -}}` (the admin-token and `iam-keys` pair), both are guarded
on an adopter setting a `platform.<name>.create`; the operators clause is
not, because the values file it exists for sets none. Raising here rather
than inside the guard is what makes both reachable from one `fail`, which is
the accumulation rule this file opens with. The guard itself is unmoved and
still decides which of THOSE TWO refusals are COLLECTED —
`test_breaking_the_guard_makes_the_modules_only_render_refuse` replaces it
with `{{- if true -}}` and reddens the modules-only render. B-U6's own
clauses, further above still, answer to none of this: each guards itself on
`hasKey .Subcharts "<name>"` or a sibling's own dial flag, independent of
`$creating` — they reach this same `fail` only because every refusal in this
file accumulates into the one `$refusals` list.
*/}}
{{- if $refusals -}}
{{- fail (printf "\n\nyadgar: this parent chart refuses to render.\n\n%s\n" (join "\n\n" $refusals)) -}}
{{- end -}}
{{- end -}}
