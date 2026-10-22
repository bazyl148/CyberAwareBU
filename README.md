<img src="docs/assets/cyberaware-lockup-light.svg" alt="CyberAware: trust the source, not the sentence." width="560">

<br>

**CyberAware is a RAG defense layer that stops knowledge-base poisoning in AI assistants.** Built and measured on [AIGoat](https://github.com/AISecurityConsortium/AIGoat), an intentionally vulnerable AI shop, presented at the Bishop's University AI Cybersecurity Challenge 2026.

**Team:** Basile, Chris and Bonté · **Focus area:** RAG security · **Read first:** [technical overview](docs/TECHNICAL-OVERVIEW.md)

## Results at a glance

AIGoat challenge CTF 7 ("Authoritative Context Poisoning"): five phrasings of the attack, asked three times at each defense level, scored by **AIGoat's own evaluator** ([full results](results/metrics.md)).

| Defense level | Attack success | Normal questions answered |
| --- | --- | --- |
| 0: no defense | 10/15 (67%) | 18/20 |
| 1: AIGoat's stock defense | 9/15 (60%) | not measured |
| 2: AIGoat + CyberAware | **0/15 (0%)** | **19/20** |

The trust gate adds a median of **0.007 ms** per request; the model's reply takes about 16 s on our CPU-only VM.

## The problem

An AI assistant that answers from a knowledge base (retrieval-augmented generation, RAG) can't tell who wrote what it retrieves. A customer's review and the legal team's refund policy look the same once they're in the prompt.

In CTF 7, a shopper posts a review claiming "support confirmed a full refund within 365 days, no receipt required". Asked about refunds, the shop assistant repeats it as official policy. The real policy is 30 days. AIGoat's own defenses don't stop it: Level 1 labels where documents came from but removes nothing, and the Level 2 scan only catches phrases like "ignore previous instructions".

AIGoat's Add Document button stands in for real ingestion paths: reviews, support tickets, wiki pages and email. The same pattern hit Microsoft 365 Copilot (EchoLeak) and Slack AI. Details and sources: [From Lab to Production](docs/FROM-LAB-TO-PRODUCTION.md).

## How CyberAware works

*Trust the source, not the sentence.* The server labels every document with its origin when it's saved, and the gate checks that label at retrieval, before the model reads anything. Rewording the attack can't get past a check that never reads the wording.

```mermaid
flowchart LR
    Q[Customer question] --> R[Retrieve top 5 documents]
    R --> P[retrieval.provenance<br/>AIGoat]
    P --> A[retrieval.acl<br/>AIGoat]
    A --> G{{cyberaware.trust_gate}}
    G -- "user-injected or untrusted tier" --> X[Removed + audit log]
    G -- "seeded, system tier" --> S[retrieval.injection_scan<br/>AIGoat]
    S --> M[Model reads trusted documents only]
```

| Component | What it does | Code |
| --- | --- | --- |
| **Trust gate** | Removes retrieved documents that users added, or whose trust tier isn't allowlisted (`system` by default) | [`overlay/cyberaware/trust_gate.py`](overlay/cyberaware/trust_gate.py) |
| **Write guard** | Visitors can't label their own documents as trusted, or edit documents they don't own | [`patches/0003-kb-write-guard.patch`](patches/0003-kb-write-guard.patch) |
| **CTF chat fix** | AIGoat's challenge chat ignored the defense level; now it applies it | [`patches/0002-challenge-chat-defense.patch`](patches/0002-challenge-chat-defense.patch) |
| **Audit log** | One JSON line per removal: time, entry, title, reason, elapsed time | [`overlay/cyberaware/audit.py`](overlay/cyberaware/audit.py) |

Everything installs as an overlay on a pinned AIGoat commit (`bb3cd1bbd1e0`) and uninstalls with one command. It is rule-based: no second AI model, because each model call costs 10–30 s on our hardware.

## Evidence

Same question at each level, captured on our VM. More in the [technical overview](docs/TECHNICAL-OVERVIEW.md#3-how-it-works).

| Level 0: flag | Level 2: no flag | Inside Level 2: the gate's decision |
| --- | --- | --- |
| <img src="docs/assets/evidence/l0-flag.png" alt="Level 0: the assistant states the 365-day policy and the flag appears" width="260"> | <img src="docs/assets/evidence/l2-no-flag.png" alt="Level 2: the real 30-day policy and no flag" width="260"> | <img src="docs/assets/evidence/trust-gate-trace.png" alt="Retrieval trace: the planted review struck through and tagged cyberaware.trust_gate" width="300"> |

## Quick start

You need AIGoat running somewhere you control. We use an Azure VM reachable only over Tailscale: see the [team setup runbook](docs/TEAM-SETUP-RUNBOOK.md). Running AIGoat locally per its own docs also works.

**1. Open AIGoat in your browser** through an SSH tunnel (the backend only accepts the `localhost` origin), then browse to http://localhost:3000:

```bash
ssh -L 3000:localhost:3000 -L 8000:localhost:8000 azureuser@<tailscale-ip>
```

**2. Install the defense** on the machine running AIGoat, then restart AIGoat:

```bash
scripts/install-overlay.sh ~/AIGoat
cd ~/AIGoat && ./scripts/stop.sh && ./scripts/start.sh
```

Defense level 0 (top bar) stays undefended so the attack can still be shown; level 2 runs our defense. The [Defense Setup and Check Guide](docs/DEFENSE-SETUP-GUIDE.md) walks the whole team through install, a harmless check, and the CTF 7 check at every level.

**3. Run the unit tests** (no model or vector store needed; about 1 second):

```bash
python3.11 -m venv ~/cyberaware-venv
~/cyberaware-venv/bin/pip install -q pytest pyyaml pydantic fastapi "sqlalchemy[asyncio]" aiosqlite httpx "python-jose[cryptography]" "passlib[bcrypt]" python-multipart
AIGOAT_DIR=~/AIGoat ~/cyberaware-venv/bin/python -m pytest tests/ -q
```

Expect `21 passed`.

**4. Measure** (on the AIGoat machine, from this repo; about 45 minutes on CPU). Writes `results/metrics.md`:

```bash
~/AIGoat/venv/bin/python eval/run_eval.py
```

For a 5-minute smoke test instead:

```bash
~/AIGoat/venv/bin/python eval/run_eval.py --runs 1 --levels 0,2 --skip-benign
```

**5. Undo** (restores stock AIGoat; restart it afterwards as in step 2):

```bash
scripts/install-overlay.sh --uninstall ~/AIGoat
```

## Documentation

| Document | For | What's in it |
| --- | --- | --- |
| [Technical overview](docs/TECHNICAL-OVERVIEW.md) | Judges, reviewers | Problem, solution, how it works, technologies, limitations |
| [From Lab to Production](docs/FROM-LAB-TO-PRODUCTION.md) | Anyone asking "is this realistic?" | Real ingestion paths, sourced incidents, what carries over |
| [Defense Setup and Check Guide](docs/DEFENSE-SETUP-GUIDE.md) | The whole team, no background needed | Install, check, CTF 7 at every level, troubleshooting, glossary |
| [Team setup runbook](docs/TEAM-SETUP-RUNBOOK.md) | Whoever runs the VM | Azure + Tailscale + AIGoat setup, daily operations, troubleshooting |
| [Prototype plan](docs/PROTOTYPE-PLAN.md) | The team | Design, status, schedule, demo run sheet, changelog |
| [Next steps](docs/NEXT-STEPS.md) | The team | Checklist up to the presentation |
| [Results](results/metrics.md) | Judges, reviewers | The latest metrics run |

## Repository layout

```
overlay/                        # our defense control package and defense profile, installed into AIGoat
patches/                        # three small AIGoat patches: register controls, CTF chat fix, write guard
scripts/install-overlay.sh      # install into an AIGoat checkout (--uninstall restores stock)
tests/                          # 21 unit tests, run against a real AIGoat checkout
eval/                           # attack and benign corpora + metrics script (run_eval.py)
results/metrics.md              # before/after numbers from the last full run
docs/                           # the documents above
docs/assets/                    # CyberAware logo (light-background versions used in docs; dark-background versions for slides) and evidence screenshots
```

## Limitations and future work

- **Labels are assumed correct.** AIGoat marks user content for free; a real ingestion pipeline must label every source correctly.
- **All-or-nothing trust.** Useful user content is removed too. A production version should quote it as "customers say", never as policy.
- **Scope.** We measured CTF 7 on the knowledge-base surface. Three more controls are designed but were cut for time: obfuscation-aware input screening (`input_guard`), delimiting retrieved text (`context_harden`) and system-prompt leak detection (`canary`).

Full discussion: [technical overview, section 5](docs/TECHNICAL-OVERVIEW.md#5-limitations-and-challenges).

## Scope and rules of engagement

- Attacks target only the team's own AIGoat instance. No scanning of other systems and no denial-of-service testing.
- No secrets are committed. The only credentials in this repo are AIGoat's published demo accounts. Flags visible in the evidence screenshots are per-account CTF codes from our own instance.

## Acknowledgements

Built on [AIGoat](https://github.com/AISecurityConsortium/AIGoat) by the AI Security Consortium (platform code Apache-2.0). Our code adds to it as an overlay and patches; AIGoat itself isn't redistributed here.
