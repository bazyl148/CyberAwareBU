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
- [ ] **Onboard teammates.** Send Tailscale invites, append each member's public key to `authorized_keys` ([runbook: Grant team members SSH access](../team-setup-runbook.md#grant-team-members-ssh-access)), and assign one AIGoat user per member.
- [ ] **Run the app in tmux** on the VM so it survives SSH drops ([runbook: Quick start](../team-setup-runbook.md#quick-start)).

## 2. Build the prototype (Mon Oct 19 – Wed Oct 21)

The design, components, owners, day-by-day schedule and gates are in **[PROTOTYPE-PLAN.md](PROTOTYPE-PLAN.md)**; track progress in its [status table](PROTOTYPE-PLAN.md#status-at-a-glance). Headline items:

- [ ] **Measure the stock Level 2 baseline first** with the [evaluation harness](PROTOTYPE-PLAN.md#evaluation-harness), so every defense is judged against real numbers.
- [ ] **Pass the Mon night gate:** `cyberaware.trust_gate` stops a CTF 7 payload, or the scope narrows to the leakage defense ([gates](PROTOTYPE-PLAN.md#schedule-and-gates)).
- [ ] **Build the remaining controls** (`context_harden`, `input_guard`, `canary`, audit log) and the [defense profile](PROTOTYPE-PLAN.md#defense-profile).
- [ ] **Plan for CPU latency.** Replies take 10–30 s, so keep the live attack to a few prompts. Prepare a fallback: a pre-recorded run or saved results.

## 3. Polish and rehearse (Thu Oct 22)

- [ ] Finish the four [deliverables](PROTOTYPE-PLAN.md#deliverables) the brief requires: working prototype, Git repo that runs from a clean clone, technical overview (problem, solution, how it works, technologies, limitations) and the live demo.
- [ ] Collect before/after metrics: attack success rate, benign pass rate and added latency ([success criteria](PROTOTYPE-PLAN.md#goal-and-success-criteria)).
- [ ] Rehearse the 10-minute [demo run sheet](PROTOTYPE-PLAN.md#demo-run-sheet) at least twice from a clean reset. It follows the brief's five points: problem and threat, solution, implementation, live demo, limitations.

## 4. Demo day (Fri Oct 23)

- [ ] Start the VM well before 13:00 and run the smoke test ([runbook: Run the smoke test](../team-setup-runbook.md#run-the-smoke-test)).
- [ ] Open the SSH tunnel and log in ahead of time; keep the fallback recording ready.
- [ ] Deallocate the VM after the presentation.

## Ground rules

- Attack only the AIGoat instance on the team's own VM. No scanning of other targets and no DoS.
- Never commit secrets: private keys, subscription IDs, real Tailscale IPs, or credentials beyond AIGoat's published demo accounts.
- Do not change the project's Python `target-version`.
- Keep the demo script reproducible from a clean reset.
