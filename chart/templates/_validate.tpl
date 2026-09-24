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
{{- $refusals := list -}}

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

{{- if $refusals -}}
{{- fail (printf "\n\nyadgar: this parent chart refuses to render.\n\n%s\n" (join "\n\n" $refusals)) -}}
{{- end -}}
{{- end -}}
{{- end -}}
