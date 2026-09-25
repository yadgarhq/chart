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
fires on the bare default render, which is load-bearing in six measured places in
`scripts/tests/test_parent_chart.py` and in the shared `helm-lint` pre-commit hook
that is part of `ci / passed` in every chart repository.

SO THE GUARD KEYS ON SOMETHING AN ADOPTER SETS: any `platform.*.create` toggle
being true. All of them are false in `platform`'s own `values.yaml`, so the
default render reaches no refusal at all, and an adopter installing the platform
layer sets at least one. ADR-0777 records the narrowing this buys and the operator
accepted it on 2026-09-22: an adopter who brings their own platform layer, with
every `create` false, is NOT refused for an empty admin token.

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

A NON-MAP `platform.operators` IS REFUSED RATHER THAN READ, and the `kindIs` arm
is there because leaving it out RAISES rather than refuses. `default` substitutes
only on an EMPTY value, so `default dict true` is `true`, and both the `create`
read and the range below would then run against a bool. Measured on helm 4.3.0
before this arm existed: `--set platform.operators=true` aborted with
`can't evaluate field create in type bool` — a stack trace where the adopter needs
a key name. `--set platform.operators=yes` does the same.

IT IS A REAL TYPO RATHER THAN A HYPOTHETICAL, and refusing it is not the same
choice the `$creating` block below makes. That block SKIPS a non-map, which is
right there: it is looking for blocks and a scalar is simply not one. Here the key
itself is the thing the parent does not offer, so a scalar under that name is an
adopter asking for the operators path in a shape no key can be read out of — and
what `platform` would do with a bool where it expects a mapping is NOT measurable
from here, because `platform` 0.1.8 has no `operators` key at all. The refusal
says what is wrong and claims nothing about that.
*/}}
{{- $operators := default dict $platform.operators -}}
{{- $operatorKeys := list -}}
{{- if not (kindIs "map" $operators) -}}
{{- $refusals = append $refusals (printf (join "" (list
      "platform.operators is a %s rather than a mapping, so no operators key can be read out of it. "
      "This parent chart offers no operators path at all: ADR-0787 rules that `platform` installs "
      "cert-manager, KEDA, mariadb-operator, Envoy Gateway and Argo CD behind operators.create, "
      "default false, in a release of its own. Remove platform.operators from this values file."))
      (kindOf $operators)) -}}
{{- else -}}
{{- if eq (default false $operators.create) true -}}
{{- $operatorKeys = append $operatorKeys "platform.operators.create" -}}
{{- end -}}
{{- range $name, $block := $operators -}}
{{- if kindIs "map" $block -}}
{{- if eq (default false $block.create) true -}}
{{- $operatorKeys = append $operatorKeys (printf "platform.operators.%s.create" $name) -}}
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

{{/* Every `platform.<name>.create` that is true, by name, in key order. */}}
{{- $creating := list -}}
{{- if kindIs "map" $platform -}}
{{- range $name, $block := $platform -}}
{{- if kindIs "map" $block -}}
{{- if eq (default false $block.create) true -}}
{{- $creating = append $creating (printf "platform.%s.create" $name) -}}
{{- end -}}
{{- end -}}
{{- end -}}
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
{{- $tokenSecret := default "" (default dict (default dict .Values.gateway).adminBootstrap).tokenSecret -}}
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
THE TRAP THE DEPENDENCY `condition` OPENS, and it is measured rather than
imagined. `platform` is declared under `condition: platform.enabled`, false in
`chart/values.yaml`. A values file stating `platform.internalCA.create: true` and
leaving `platform.enabled` alone reads as a fully configured platform layer and
renders NOTHING of it — measured 2026-09-24 on helm 3.18.4: the same 32 objects as
the bare default, exit 0, no warning. The refusal names both keys because the file
that trips it names only one.
*/}}
{{- if ne (default false $platform.enabled) true -}}
{{- $refusals = append $refusals (printf (join "" (list
      "platform.enabled is not true and %s asks for the platform layer. `platform` is declared under "
      "`condition: platform.enabled`, so this render contains NONE of the objects those toggles name — "
      "no Issuer, no Certificate, no Gateway, no bootstrap Job — while reading as fully configured. "
      "Set platform.enabled true, or set those create toggles false."))
      $asked) -}}
{{- end -}}
{{- end -}}

{{/*
THE ONE `fail`, AND IT SITS OUTSIDE THE `$creating` GUARD SO THE ADR-0787 CLAUSE
CAN REACH IT. Every refusal above `{{- if $creating -}}` is guarded on an adopter
setting a `platform.<name>.create`; the operators clause is not, because the values
file it exists for sets none. Raising here rather than inside the guard is what
makes both reachable from one `fail`, which is the accumulation rule this file
opens with. The guard itself is unmoved and still decides which refusals are
COLLECTED — `test_breaking_the_guard_makes_the_default_render_refuse` replaces it
with `{{- if true -}}` and still reddens the bare default render.
*/}}
{{- if $refusals -}}
{{- fail (printf "\n\nyadgar: this parent chart refuses to render.\n\n%s\n" (join "\n\n" $refusals)) -}}
{{- end -}}
{{- end -}}
