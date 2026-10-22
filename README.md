<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/assets/cyberaware-lockup-dark.svg">
  <img src="docs/assets/cyberaware-lockup-light.svg" alt="CyberAware: trust the source, not the sentence." width="560">
</picture>

# CyberAwareBU

**Team:** Basile, Chris and Bonté · Bishop's University

A defense layer for RAG-based LLM applications, built and demonstrated against [AIGoat](https://github.com/AISecurityConsortium/AIGoat), an intentionally vulnerable LLM app. Submitted to the AI Cybersecurity Challenge 2026.

> **Status:** prototype complete and installed on the team VM; demo Fri Oct 23, 2026. Start with the **[technical overview](docs/TECHNICAL-OVERVIEW.md)**. Component status: [prototype plan](docs/PROTOTYPE-PLAN.md#status-at-a-glance).

## Problem

LLM apps that use retrieval-augmented generation (RAG) trust whatever lands in their knowledge base. An attacker who can plant content there, or slip instructions into a prompt, can steer the model into leaking data or ignoring its guardrails.

In AIGoat the attacker plants content through an Add Document button. In production they never need one: they write a review, support ticket, wiki page or email that the company's own pipeline indexes. See [From Lab to Production](docs/FROM-LAB-TO-PRODUCTION.md) for real paths, known incidents and the limits of our defense.

## Approach

The defense decides trust by **where a document came from, not by what it says**, and enforces it at retrieval, before the model reads anything. It's an overlay on AIGoat, not a fork:

| Component | Purpose |
| --- | --- |
| Trust gate (`cyberaware.trust_gate`) | After retrieval, removes documents that users added or whose trust tier isn't allowlisted; the shop's own documents still reach the model |
| CTF chat fix (patch P1) | Makes AIGoat's challenge chat apply the defense level, which stock AIGoat skips |
| Write guard (patch P3) | Stops users from labelling their own documents as trusted or editing documents they don't own |
| Audit log | Records every document the gate removed, with the reason |

`eval/run_eval.py` runs the same attack at each defense level, scores every reply with AIGoat's own CTF 7 evaluator, and writes [results/metrics.md](results/metrics.md).

**Future work** (designed, cut for time): obfuscation-aware input screening (`input_guard`), delimiting and cleaning retrieved text (`context_harden`) and system-prompt leak detection (`canary`). See [Limitations](docs/TECHNICAL-OVERVIEW.md#5-limitations-and-challenges).

## Repository layout

```
overlay/                        # our defense controls package and defense profile, installed into AIGoat
patches/                        # three small AIGoat patches (register controls, CTF chat defense, KB write guard)
scripts/install-overlay.sh      # install into ~/AIGoat (or --uninstall to restore stock)
tests/                          # unit tests, run against a real AIGoat checkout
eval/                           # attack and benign corpora + metrics script (run_eval.py)
results/metrics.md              # before/after numbers from the last full run
docs/assets/                    # CyberAware logo: mark and light/dark lockups (SVG)
docs/TECHNICAL-OVERVIEW.md      # problem, solution, how it works, technologies, limitations
docs/TEAM-SETUP-RUNBOOK.md      # deploying AIGoat on Azure behind Tailscale
docs/DEFENSE-SETUP-GUIDE.md     # install the defense, check it, run the CTF 7 check
docs/FROM-LAB-TO-PRODUCTION.md  # how CTF 7 maps to real apps, known incidents, our limits
docs/PROTOTYPE-PLAN.md          # living design plan: components, schedule, gates, status
docs/NEXT-STEPS.md              # checklist up to the presentation
```

See [docs/PROTOTYPE-PLAN.md](docs/PROTOTYPE-PLAN.md#repository-layout-and-install) for the full planned layout.

## Getting started

1. **Deploy AIGoat.** Follow the [team setup runbook](docs/TEAM-SETUP-RUNBOOK.md) to run it on an Azure VM reachable only over Tailscale. Running it locally per the AIGoat docs also works.
2. **Open the app.** Forward the app ports over SSH and browse to `http://localhost:3000`:
   ```bash
   ssh -L 3000:localhost:3000 -L 8000:localhost:8000 azureuser@<tailscale-ip>
   ```
3. **Install the defense** on the machine running AIGoat, then restart AIGoat. Step-by-step for the whole team, including a harmless check that it works: **[Defense Setup and Check Guide](docs/DEFENSE-SETUP-GUIDE.md)**.
   ```bash
   scripts/install-overlay.sh ~/AIGoat
   cd ~/AIGoat && ./scripts/stop.sh && ./scripts/start.sh
   ```
   Defense level 0 (navbar) stays undefended; level 2 runs our defense, including on the CTF challenges. `scripts/install-overlay.sh --uninstall ~/AIGoat` restores stock AIGoat.
4. **Run the tests** (no Ollama needed): see [Repository layout and install](docs/PROTOTYPE-PLAN.md#repository-layout-and-install).
5. **Measure** (on the VM, about 45 minutes on CPU): `~/AIGoat/venv/bin/python eval/run_eval.py`

## Results

CTF 7, five phrasings asked three times per level, scored by AIGoat's own evaluator ([full results](results/metrics.md)):

| Defense level | Attack success | Benign questions answered |
| --- | --- | --- |
| 0: none | 10/15 (67%) | 18/20 |
| 1: AIGoat stock | 9/15 (60%) | not measured |
| 2: AIGoat + CyberAware | **0/15 (0%)** | **19/20** |

The trust gate adds a median of 0.007 ms per request.

## Scope and rules of engagement

- Attacks target only the team's own AIGoat instance. No scanning of other systems and no denial-of-service testing.
- No secrets are committed. The only credentials in this repo are AIGoat's published demo accounts.

## Acknowledgements

Built on [AIGoat](https://github.com/AISecurityConsortium/AIGoat) by the AI Security Consortium.
