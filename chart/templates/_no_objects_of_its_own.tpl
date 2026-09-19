{{/*
THIS PARENT RENDERS NO OBJECTS OF ITS OWN, AND THIS FILE IS HOW IT SAYS SO.

A parent that renders a Deployment, a Service or a ConfigMap of its own becomes a
ninth module nobody declared — ADR-0723 names that outcome in its own
`revisit_trigger`, as the thing that would change what was authorised. Every one
of the 38 objects an install of this chart produces comes from one of the eight
subcharts, each of which is reviewed, gated and released in its own repository.

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
nothing. Measured: with this file present the chart renders the same 38 objects
it rendered before the directory existed, and `helm lint --strict` passes.

A `NOTES.txt` would also satisfy the linter and was rejected: it prints to an
installer's terminal, so it is a place a future contributor may reasonably add
text, and text is one edit away from a template. A partial that defines nothing
is the shape with nowhere to grow.

IF YOU ARE HERE TO ADD A TEMPLATE, THAT IS THE DECISION TO BRING TO THE RECORD
rather than a file to add. An object this chart needs that no module owns is
either a module's object in the wrong repository or a new module.
*/}}
