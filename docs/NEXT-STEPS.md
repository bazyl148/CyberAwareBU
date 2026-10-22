# Next Steps

Plan for getting from a working AIGoat environment to a rehearsed demo for the AI Cybersecurity Challenge 2026.

**Presentation:** Fri Oct 23, 2026, 13:00, 10 minutes, demo-first.
**Deliverables:** working prototype, Git repo, brief technical overview, live demo.

## Current status

- [x] AIGoat running on a CPU-only Azure VM, reachable over Tailscale ([runbook](TEAM-SETUP-RUNBOOK.md))
- [x] Sanitized setup runbook merged into `main`
- [x] Team registration confirmed
- [x] Prototype built and installed on the VM: trust gate, CTF chat fix, write guard, audit log ([guide](DEFENSE-SETUP-GUIDE.md))
- [x] CTF 7 check passed on the VM: flag at Levels 0 and 1, none at Level 2
- [x] Scope decided: `context_harden`, `input_guard` and `canary` cut for time, presented as future work

## 1. Wed Oct 21, tonight

- [x] **Level 2 evidence:** the Retrieval trace shows the review removed by `cyberaware.trust_gate`, and the audit log records it for `charlie`. Screenshots are in [`docs/assets/evidence/`](assets/evidence/).
- [ ] **Run AIGoat in tmux** on the VM so it survives SSH drops ([runbook: Quick start](TEAM-SETUP-RUNBOOK.md#quick-start)):

  ```bash
  tmux new -s aigoat          # or: tmux attach -t aigoat
  cd ~/AIGoat && ./scripts/stop.sh && ./scripts/start.sh
  ```

  Then press **Ctrl+b**, then **d**, to leave it running.

## 2. Thu Oct 22, morning (feature freeze at 12:00)

- [x] **Metrics:** full run done Oct 22 02:15 UTC; [`results/metrics.md`](../results/metrics.md) is in the repo. Re-run after any change (about 45 minutes, on the VM):

  ```bash
  cd ~/CyberAwareBU && ~/AIGoat/venv/bin/python eval/run_eval.py
  ```
- [ ] **Hotspot test:** the venue network is restricted. On the phone hotspot: Tailscale up, SSH tunnel, log in at http://localhost:3000, one chat reply. If SSH hangs, apply the [MTU fix](TEAM-SETUP-RUNBOOK.md#ssh-hangs-but-ping-works).
- [ ] **Ask the organizers** where and by when to submit the repo and technical overview.
- [ ] **Review** the [technical overview](TECHNICAL-OVERVIEW.md), README and slides.
- [ ] **Merge** `dev/cyberaware` into `main` and push. Clean-clone check: clone `main` on the VM, re-run `install-overlay.sh` (expect `Already applied`) and the 21 unit tests.

## 3. Thu Oct 22, afternoon

- [ ] Record the full demo as a backup video. On a restricted network, it is the real fallback.
- [ ] Rehearse the [demo run sheet](PROTOTYPE-PLAN.md#demo-run-sheet) twice, each time from a reset and the pre-stage checklist; once over the hotspot. Each account can play CTF 7 only once, so reset before every rehearsal.
- [ ] Optional: delete the temporary NSG rule now that Tailscale SSH is confirmed:
  ```bash
  az network nsg rule delete -g $RG --nsg-name nsg-aigoat -n AllowInboundSSH
  ```

## 4. Demo day (Fri Oct 23)

- [ ] Start the VM well before 13:00 and run the smoke test ([runbook: Run the smoke test](TEAM-SETUP-RUNBOOK.md#run-the-smoke-test)).
- [ ] Work through the [pre-stage checklist](PROTOTYPE-PLAN.md#demo-run-sheet), starting 45 minutes before.
- [ ] Deallocate the VM after the presentation.

## Ground rules

- Attack only the AIGoat instance on the team's own VM. No scanning of other targets and no DoS.
- Never commit secrets: private keys, subscription IDs, real Tailscale IPs, or credentials beyond AIGoat's published demo accounts.
- Do not change the project's Python `target-version`.
- Keep the demo script reproducible from a clean reset.
