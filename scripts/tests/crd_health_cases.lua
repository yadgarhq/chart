-- Behaviour cases for the CRD health override in bootstrap/argocd-values.yaml
-- (ledger 1197). Argo CD runs health scripts in gopher-lua, which is Lua 5.1.
--
-- CI HAS NO Lua RUNTIME, so CI does not run this file. CI pins the script's
-- bytes instead (scripts/tests/test_argocd_values.py). Run it locally:
--
--   python3 scripts/tests/test_argocd_values.py > /tmp/crd-health.lua
--   nix shell nixpkgs#lua5_1 -c lua scripts/tests/crd_health_cases.lua /tmp/crd-health.lua
--
-- Exit 0 and "N/N passed" means every case matches.

local path = assert(arg[1], "usage: lua crd_health_cases.lua <health.lua>")
local f = assert(io.open(path, "r"))
local source = f:read("*a")
f:close()
local chunk = assert(loadstring(source, "health.lua"))

local function cond(type_, status, reason, message)
  return { type = type_, status = status, reason = reason, message = message or "" }
end

local cases = {
  {
    name = "no conditions",
    obj = { metadata = {}, status = { conditions = {} } },
    want = "Progressing",
  },
  {
    -- The measured gateway-api state: the API server writes the approval
    -- condition about 2 s before NamesAccepted and Established.
    name = "KubernetesAPIApprovalPolicyConformant only",
    obj = { metadata = {}, status = { conditions = {
      cond("KubernetesAPIApprovalPolicyConformant", "True", "ApprovedAnnotation"),
    } } },
    want = "Progressing",
  },
  {
    name = "Established False, reason Installing",
    obj = { metadata = {}, status = { conditions = {
      cond("NamesAccepted", "True", "NoConflicts"),
      cond("Established", "False", "Installing"),
    } } },
    want = "Progressing",
  },
  {
    name = "Established True",
    obj = { metadata = {}, status = { conditions = {
      cond("NamesAccepted", "True", "NoConflicts"),
      cond("Established", "True", "InitialNamesAccepted"),
    } } },
    want = "Healthy",
  },
  {
    name = "NamesAccepted False",
    obj = { metadata = {}, status = { conditions = {
      cond("NamesAccepted", "False", "MultipleConflicts", "plural is already in use"),
    } } },
    want = "Degraded",
  },
  {
    -- Keeps upstream's Degraded for an Established condition that is False for
    -- a reason other than Installing. Catches a change that maps every
    -- not-yet-Established state to Progressing.
    name = "Established False, reason other than Installing",
    obj = { metadata = {}, status = { conditions = {
      cond("NamesAccepted", "True", "NoConflicts"),
      cond("Established", "False", "NotEstablished"),
    } } },
    want = "Degraded",
  },
}

local passed = 0
for _, c in ipairs(cases) do
  setfenv(chunk, setmetatable({ obj = c.obj }, { __index = _G }))
  local ok, hs = pcall(chunk)
  local got = ok and hs.status or ("error: " .. tostring(hs))
  local msg = ok and hs.message or ""
  if got == c.want then
    passed = passed + 1
    print(string.format("ok    %-50s %s (%s)", c.name, got, msg))
  else
    print(string.format("FAIL  %-50s want %s, got %s (%s)", c.name, c.want, got, msg))
  end
end
print(string.format("%d/%d passed", passed, #cases))
os.exit(passed == #cases and 0 or 1)
