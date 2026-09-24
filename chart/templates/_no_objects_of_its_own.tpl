{{/*
THIS PARENT RENDERS NO OBJECTS OF ITS OWN, AND THIS FILE IS HOW IT SAYS SO.

A parent that renders a Deployment, a Service or a ConfigMap of its own becomes a
module nobody declared — ADR-0723 names that outcome in its own `revisit_trigger`,
as the thing that would change what was authorised. Every object an install of
this chart produces comes from one of its declared subcharts, each of which is
reviewed, gated and released in its own repository.

SO WHY DOES `templates/` EXIST AT ALL. Because `helm lint --strict` REFUSES a
chart without it, and `helm lint --strict` is what the shared `helm-lint`
pre-commit hook runs and therefore part of `ci / passed`. Measured on helm 4.2.3
and 3.20.2:

  [WARNING] templates/: directory does not exist
  Error: 1 chart(s) linted, 1 chart(s) failed

`--strict` promotes that warning to a failure. git cannot hold an empty
directory, so the directory needs a file in it, and the file must render nothing.

A FILE WHOSE NAME BEGINS WITH `_` IS A PARTIAL. helm loads it and emits nothing
from it unless something calls a definition inside it, and this file defines
nothing. Measured: with this file present the chart renders the same objects it
rendered before the directory existed, and `helm lint --strict` passes.

A `NOTES.txt` would also satisfy the linter and was rejected: it prints to an
installer's terminal, so it is a place a future contributor may reasonably add
text, and text is one edit away from a template. A partial that defines nothing
is the shape with nowhere to grow.

IF YOU ARE HERE TO ADD A TEMPLATE, THAT IS THE DECISION TO BRING TO THE RECORD
rather than a file to add. An object this chart needs that no module owns is
either a module's object in the wrong repository or a new module.

IT HAS BEEN BROUGHT TO THE RECORD ONCE, AND THE RECORD IS ADR-0777. `validate.yaml`
beside this file is a non-partial: helm renders it, and it EMITS NOTHING. Its only
content is an include of `_validate.tpl`, which refuses an install whose values
would produce an estate nobody can create a user in. It exists because a `fail`
inside a partial never executes — a partial runs only when something includes it —
so the call has to sit in a rendered template.

THE RULE DID NOT ERODE; IT WAS RULED ON, ONCE, FOR A FILE THAT RENDERS NOTHING.
`test_the_templates_directory_holds_only_partials` permits exactly that one name
and refuses the next, and it asserts that this chart's own render is still empty
rather than assuming it. A second non-partial needs its own ruling and its own
amendment to that test. That cost is the intended one.
*/}}
