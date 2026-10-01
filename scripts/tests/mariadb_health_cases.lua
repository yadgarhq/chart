-- Behaviour cases for the MariaDB health override in bootstrap/argocd-values.yaml
-- (ledger 1205). Argo CD runs health scripts in gopher-lua, which is Lua 5.1.
--
-- CI HAS NO Lua RUNTIME, so CI does not run this file. CI pins the script's
-- bytes instead (scripts/tests/test_argocd_values.py). Run it locally:
--
--   python3 scripts/tests/test_argocd_values.py mariadb > /tmp/mariadb-health.lua
--   nix shell nixpkgs#lua5_1 -c lua scripts/tests/mariadb_health_cases.lua /tmp/mariadb-health.lua
--
-- Exit 0 and "N/N passed" means every case matches.

local path = assert(arg[1], "usage: lua mariadb_health_cases.lua <health.lua>")
local f = assert(io.open(path, "r"))
local source = f:read("*a")
f:close()
local chunk = assert(loadstring(source, "health.lua"))

local function ready(status, reason, message)
  return { type = "Ready", status = status, reason = reason, message = message }
end

local function mariadb(name, conditions)
  local obj = { metadata = { name = name, namespace = "yadgar" } }
  if conditions ~= nil then
    obj.status = { conditions = conditions }
  end
  return obj
end

-- The message measured on 2026-10-01 for MariaDB yadgar/task-db-mariadb.
local GRANT_NOT_FOUND = 'Error reconciling SQL: error getting mariadb.sys Grant: '
  .. 'Grant.k8s.mariadb.com "task-db-mariadb-mariadb-sys-global-priv" not found'

local cases = {
  -- The four cases ledger 1205 asks for.
  {
    name = "Ready True",
    obj = mariadb("task-db-mariadb", { ready("True", "StatefulSetReady", "Running") }),
    want = "Healthy",
  },
  {
    name = "mariadb.sys Grant not found (operator cache race)",
    obj = mariadb("task-db-mariadb", { ready("False", "Failed", GRANT_NOT_FOUND) }),
    want = "Progressing",
  },
  {
    name = "terminal reconcile error",
    obj = mariadb("task-db-mariadb", {
      ready("False", "Failed", "Error reconciling StatefulSet: error creating StatefulSet: "
        .. 'StatefulSet.apps "task-db-mariadb" is invalid'),
    }),
    want = "Degraded",
  },
  {
    name = "no status",
    obj = mariadb("task-db-mariadb", nil),
    want = "Progressing",
  },

  -- Near misses: each catches a match broader than the one race.
  {
    -- Another MariaDB's Grant name: not this object's own race.
    name = "Grant not found, name of another MariaDB",
    obj = mariadb("iam-db-mariadb", { ready("False", "Failed", GRANT_NOT_FOUND) }),
    want = "Degraded",
  },
  {
    name = "mariadb.sys Grant read fails for another reason",
    obj = mariadb("task-db-mariadb", {
      ready("False", "Failed", "Error reconciling SQL: error getting mariadb.sys Grant: "
        .. "Get \"https://10.96.0.1:443\": dial tcp 10.96.0.1:443: connect: connection refused"),
    }),
    want = "Degraded",
  },
  {
    name = "not found in another phase",
    obj = mariadb("task-db-mariadb", {
      ready("False", "Failed", "Error reconciling Secret: error getting Secret: "
        .. 'Secret "task-db-root" not found'),
    }),
    want = "Degraded",
  },
  {
    -- The exact message, with a different condition type.
    name = "Grant message on a condition that is not Ready",
    obj = mariadb("task-db-mariadb", {
      { type = "Updated", status = "False", reason = "Failed", message = GRANT_NOT_FOUND },
    }),
    want = "Degraded",
  },
  {
    name = "Grant not found, no metadata.name",
    obj = { metadata = {}, status = { conditions = { ready("False", "Failed", GRANT_NOT_FOUND) } } },
    want = "Degraded",
  },

  {
    name = "Grant not found, no metadata",
    obj = { status = { conditions = { ready("False", "Failed", GRANT_NOT_FOUND) } } },
    want = "Degraded",
  },
  {
    -- Exact comparison: a trailing period is another message.
    name = "Grant not found with a trailing period",
    obj = mariadb("task-db-mariadb", { ready("False", "Failed", GRANT_NOT_FOUND .. ".") }),
    want = "Degraded",
  },
  {
    -- The second race this hunk does NOT cover: the cache still lags on the
    -- next reconcile, so the Create returns AlreadyExists. Stays Degraded.
    name = "mariadb.sys Grant already exists (second race)",
    obj = mariadb("task-db-mariadb", {
      ready("False", "Failed", "Error reconciling SQL: error reconciling mariadb.sys user auth: "
        .. "error reconciling Grant: grants.k8s.mariadb.com "
        .. '"task-db-mariadb-mariadb-sys-global-priv" already exists'),
    }),
    want = "Degraded",
  },
  {
    -- Mixed order: a True condition first, then the race on Ready.
    name = "True condition, then Grant not found on Ready",
    obj = mariadb("task-db-mariadb", {
      { type = "Initialized", status = "True", reason = "Initialized", message = "Initialized" },
      ready("False", "Failed", GRANT_NOT_FOUND),
    }),
    want = "Progressing",
  },
  {
    -- Upstream returns on the FIRST False condition; a terminal error that
    -- comes first stays Degraded even when Ready carries the race.
    name = "terminal False condition first, then the race on Ready",
    obj = mariadb("task-db-mariadb", {
      { type = "Updated", status = "False", reason = "Failed", message = "Error updating" },
      ready("False", "Failed", GRANT_NOT_FOUND),
    }),
    want = "Degraded",
  },

  -- Upstream's six testdata cases, status blocks and expected messages as in
  -- argo-cd v3.1.8 resource_customizations/k8s.mariadb.com/MariaDB/
  -- (health_test.yaml and testdata/*.yaml).
  {
    name = "upstream no_status",
    obj = { metadata = { name = "mariadb-server" }, status = { revision = 0 } },
    want = "Progressing", want_msg = "No status info available",
  },
  {
    name = "upstream statefulset_ready",
    obj = mariadb("mariadb-server", { ready("True", "StatefulSetReady", "Running") }),
    want = "Healthy", want_msg = "Running",
  },
  {
    name = "upstream statefulset_not_ready",
    obj = mariadb("mariadb-server", { ready("False", "StatefulSetNotReady", "Not ready") }),
    want = "Progressing", want_msg = "Not ready",
  },
  {
    name = "upstream restore_complete",
    obj = mariadb("mariadb-server", {
      { type = "Bootstrapped", status = "True", reason = "RestoreComplete", message = "Ready" },
      ready("True", "RestoreComplete", "Running"),
    }),
    want = "Healthy", want_msg = "Running",
  },
  {
    name = "upstream restore_not_complete",
    obj = mariadb("mariadb-server", {
      ready("False", "RestoreNotComplete", "Restoring backup"),
      { type = "Bootstrapped", status = "False", reason = "RestoreNotComplete", message = "Not ready" },
    }),
    want = "Progressing", want_msg = "Restoring backup",
  },
  {
    name = "upstream mariadb_error",
    obj = mariadb("mariadb-server", { ready("False", "Failed", "Error creating ConfigMap") }),
    want = "Degraded", want_msg = "Error creating ConfigMap",
  },
}

local passed = 0
for _, c in ipairs(cases) do
  setfenv(chunk, setmetatable({ obj = c.obj }, { __index = _G }))
  local ok, hs = pcall(chunk)
  local got = ok and hs.status or ("error: " .. tostring(hs))
  local msg = ok and hs.message or ""
  if got == c.want and (c.want_msg == nil or msg == c.want_msg) then
    passed = passed + 1
    print(string.format("ok    %-52s %s (%s)", c.name, got, msg))
  else
    print(string.format("FAIL  %-52s want %s (%s), got %s (%s)", c.name, c.want,
      c.want_msg or "any message", got, msg))
  end
end
print(string.format("%d/%d passed", passed, #cases))
os.exit(passed == #cases and 0 or 1)
