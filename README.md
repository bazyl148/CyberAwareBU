# CyberAwareBU

A defense layer for RAG-based LLM applications, built and demonstrated against [AIGoat](https://github.com/AISecurityConsortium/AIGoat), an intentionally vulnerable LLM app. Submitted to the AI Cybersecurity Challenge 2026.

> **Status:** work in progress. The environment is set up and the prototype is under development. See [docs/NEXT-STEPS.md](docs/NEXT-STEPS.md).

## Problem

LLM apps that use retrieval-augmented generation (RAG) trust whatever lands in their knowledge base. An attacker who can plant content there, or slip instructions into a prompt, can steer the model into leaking data or ignoring its guardrails.

## Approach

The defense is a layer applied on top of AIGoat, not a fork:

| Component | Purpose |
| --- | --- |
| Provenance-aware RAG | Tags retrieved content with its source and trust level, so untrusted documents cannot act as instructions |
| Input/output guard | Screens prompts and responses for injection patterns and sensitive data |
| Canary tokens | Planted markers that reveal when protected content leaks |
| Audit log | Records detections and blocked requests for review |

A demo script runs the same attack before and after the defense is applied and reports the difference.

## Repository layout

```
defense/                 # defense layer applied on top of AIGoat (planned)
scripts/demo.sh          # attack -> apply defense -> re-attack (planned)
docs/NEXT-STEPS.md       # plan and checklist up to the presentation
team-setup-runbook.md    # deploying AIGoat on Azure behind Tailscale
```

## Getting started

1. **Deploy AIGoat.** Follow [team-setup-runbook.md](team-setup-runbook.md) to run it on an Azure VM reachable only over Tailscale. Running it locally per the AIGoat docs also works.
2. **Open the app.** Forward the app ports over SSH and browse to `http://localhost:3000`:
   ```bash
   ssh -L 3000:localhost:3000 -L 8000:localhost:8000 azureuser@<tailscale-ip>
   ```
3. **Run the demo.** Instructions will be added here once `scripts/demo.sh` is in place.

## Results

Before/after metrics (attack success rate, canary token hits, added latency) will be published here.

## Scope and rules of engagement

- Attacks target only the team's own AIGoat instance. No scanning of other systems and no denial-of-service testing.
- No secrets are committed. The only credentials in this repo are AIGoat's published demo accounts.

## Acknowledgements

Built on [AIGoat](https://github.com/AISecurityConsortium/AIGoat) by the AI Security Consortium.
