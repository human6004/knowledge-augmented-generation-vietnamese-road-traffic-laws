import assert from "node:assert/strict"
import { homeFor } from "../src/auth-policy.ts"
assert.equal(homeFor("user"), "/chat")
assert.equal(homeFor("admin"), "/admin/dashboard")
console.log("Role routing checks passed")
