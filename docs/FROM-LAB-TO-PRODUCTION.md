# From Lab to Production

Why CTF 7 matters outside AIGoat: how the same flaw shows up in real applications, what our defense carries over, and where it stops.

---

## Contents

- [The stand-in, stated plainly](#the-stand-in-stated-plainly)
- [Real ways outside content reaches a knowledge base](#real-ways-outside-content-reaches-a-knowledge-base)
- [It has already happened](#it-has-already-happened)
- [What carries over from our defense](#what-carries-over-from-our-defense)
- [What doesn't carry over](#what-doesnt-carry-over)
- [On stage](#on-stage)

---

## The stand-in, stated plainly

In CTF 7, a visitor clicks **Add Document** and writes straight into the assistant's knowledge base. No real application offers that button. It is AIGoat's shortcut for an **ingestion pipeline**: the automated jobs that collect reviews, tickets, wiki pages, files and emails and index them so the assistant can search them.

In production the attacker never sees a knowledge-base screen. They write ordinary content that the company's own pipeline picks up. Once indexed, that content usually loses any record of who wrote it, and the model treats a stranger's text and the legal team's policy as equally true. That loss of origin is the real flaw, and it is the part CTF 7 simulates faithfully.

[↑ Back to top](#contents)

---

## Real ways outside content reaches a knowledge base

| Path | Who writes it | What the poisoned version looks like |
| --- | --- | --- |
| **Product reviews and Q&A** | Any customer | A 5-star review that "quotes" a 365-day refund policy, which the shop assistant then repeats as fact |
| **Support tickets** | Any customer | A ticket stating a fake promise ("support confirmed a free replacement"), indexed so the bot can learn from past cases |
| **Shared wikis** (Confluence, SharePoint, Notion) | Employees, contractors, sometimes guests | One edited page becomes "official policy" for the internal assistant |
| **Web pages the assistant searches** | Anyone who publishes online | Search-engine poisoning aimed at the AI instead of a person |
| **Uploaded files** (resumes, invoices, contracts) | Applicants, suppliers, clients | Hidden white-on-white text that tells the screening assistant what to conclude |
| **Email and chat assistants** | Anyone who can send you a message | An email whose text the assistant reads and acts on when you ask it a question |

[↑ Back to top](#contents)

---

## It has already happened

- **EchoLeak, Microsoft 365 Copilot (CVE-2025-32711, CVSS 9.3, fixed June 2025).** Aim Security showed that a crafted email, never opened by the victim, could make Copilot pull in private data through hidden instructions. Aim reported that writing the email in plain, non-technical language got it past Microsoft's injection classifiers. [Microsoft advisory](https://msrc.microsoft.com/update-guide/vulnerability/CVE-2025-32711) · [coverage](https://thehackernews.com/2025/06/zero-click-ai-vulnerability-exposes.html)
- **Slack AI (PromptArmor, August 2024).** A message posted in a public channel could make Slack AI leak data from private channels the attacker wasn't in. Slack's first response called the behaviour intended, since public messages are searchable by design. [PromptArmor write-up](https://promptarmor.com/resources/data-exfiltration-from-slack-ai-via-indirect-prompt-injection)
- **PoisonedRAG (Zou et al., USENIX Security 2025).** Researchers added five crafted texts per target question to a knowledge base of millions and steered the answer about 90% of the time. The defenses they tested, including paraphrasing and perplexity checks, were insufficient. [Paper](https://www.usenix.org/conference/usenixsecurity25/presentation/zou)

[↑ Back to top](#contents)

---

## What carries over from our defense

The principle behind the [trust gate](DEFENSE-SETUP-GUIDE.md#defenses) applies to any of the paths above:

1. **Record each document's origin when it is ingested**: review, ticket, wiki, the company's own policy. Store it as a label that the content's author can't change.
2. **Check that label when retrieving**, before the model reads anything, and keep untrusted content out of the parts of the answer that state facts or policy.

The gate decides by **label, not by wording**. A pattern scan misses an attack written in normal language, as both AIGoat's own injection scan and the EchoLeak classifiers did. A label check does not care how persuasive the text is.

[↑ Back to top](#contents)

---

## What doesn't carry over

- **Labelling is the hard part, and AIGoat gives it away.** In AIGoat the server marks every Add Document entry as user-injected. A real pipeline must assign trust correctly for every source, and keep it correct when content is copied, merged or edited. Our prototype assumes the labels are right.
- **All-or-nothing trust is too blunt.** Our gate removes every untrusted document. In production, much user content is useful: you want the assistant to know reviewers say a hoodie runs small. A production version needs a middle path:
  - Let user content inform answers, but attribute it ("customers say…"), never as "our policy is…".
  - Never let it override a trusted document.
  - Keep it separate from the model's instructions.
- **Trusted sources can be poisoned too.** If an attacker can edit a wiki page that is labelled trusted, the label is wrong. Our write guard covers this inside AIGoat only.

[↑ Back to top](#contents)

---

## On stage

For the opening minute of the demo:

> "AIGoat's Add Document button is a stand-in for any ingestion path: reviews, support tickets, wiki pages, email. In production the attacker never sees a knowledge-base screen; they write a review, and the company's own pipeline does the rest. Microsoft 365 Copilot and Slack AI have both been hit this way."

[↑ Back to top](#contents)
