# Next Steps

Plan for getting from a working AIGoat environment to a rehearsed demo for the AI Cybersecurity Challenge 2026.

**Presentation:** Fri Oct 23, 2026, 13:00, 10 minutes, demo-first.
**Deliverables:** working prototype, Git repo, brief technical overview, live demo.

## Current status

- [x] AIGoat running on a CPU-only Azure VM, reachable over Tailscale ([runbook](../team-setup-runbook.md))
- [x] Sanitized setup runbook merged into `main`
- [ ] Team registration confirmed
- [ ] Prototype started

## 1. Blockers and quick wins (Mon Oct 19)

- [ ] **Confirm team registration.** The deadline was Oct 9 with no extensions; everything else depends on it.
- [ ] **Close public SSH.** Once SSH over Tailscale works, delete the temporary NSG rule:
  ```bash
  az network nsg rule delete -g $RG --nsg-name nsg-aigoat -n AllowInboundSSH
  ```
  Verify that SSH to the public IP times out and the Tailscale address still connects.
- [ ] **Onboard teammates.** Send Tailscale invites, append each member's public key to `authorized_keys` (runbook Step 5), and assign one AIGoat user per member.
- [ ] **Run the app in tmux** on the VM so it survives SSH drops (runbook Step 6).

## 2. Build the prototype (Mon Oct 19 – Wed Oct 21)

- [ ] **Scaffold the repo:**
  ```
  defense/          # patch or layer applied on top of AIGoat
  scripts/demo.sh   # attack -> apply defense -> re-attack
  docs/STRATEGY.md  # challenge strategy
  README.md
  ```
- [ ] **Write the attack → defend → re-attack script before any defense code.** Pick one RAG poisoning or prompt injection attack that reliably succeeds at AIGoat's lowest defense level, and make it reproducible from a clean reset (`./scripts/stop.sh --clean && ./scripts/start.sh`). It is the backbone of the demo and of the metrics.
- [ ] **Add defenses one at a time**, re-running the script after each:
  - [ ] Provenance tagging on knowledge-base and RAG content
  - [ ] Input/output guard
  - [ ] Canary tokens to detect leakage
  - [ ] Audit log
- [ ] **Plan for CPU latency.** Replies take 10–30 s, so keep the live attack to a few prompts. Prepare a fallback: a pre-recorded run or saved results.

## 3. Polish and rehearse (Thu Oct 22)

- [ ] Write the one-page technical overview and finish the README.
- [ ] Collect before/after metrics:
  - Attack success rate, with and without the defense
  - Canary token hits
  - Latency added by the guards
- [ ] Rehearse the full 10-minute demo at least twice from a clean reset.

## 4. Demo day (Fri Oct 23)

- [ ] Start the VM well before 13:00 and run the smoke test (runbook Step 7).
- [ ] Open the SSH tunnel and log in ahead of time; keep the fallback recording ready.
- [ ] Deallocate the VM after the presentation.

## Ground rules

- Attack only the AIGoat instance on the team's own VM. No scanning of other targets and no DoS.
- Never commit secrets: private keys, subscription IDs, real Tailscale IPs, or credentials beyond AIGoat's published demo accounts.
- Do not change the project's Python `target-version`.
- Keep the demo script reproducible from a clean reset.
