# Defense Setup and Check Guide

How to switch our defense on in the team's AIGoat, check that it works, and run the CTF 7 check before the demo. No security or programming background needed: every step says what to type, what you should see, and what to do if you see something else.

**Time:** about 30 minutes · **You need:** the [runbook](../team-setup-runbook.md) setup done (VM, Tailscale, the `aigoat-start.sh` script) · **Applies to:** AIGoat commit `bb3cd1bbd1e0`

---

## Contents

- [The idea in one minute](#the-idea-in-one-minute)
- [Words used in this guide](#words-used-in-this-guide)
- [Who does what](#who-does-what)
- [Part A: Install the defense (one person, once)](#part-a-install-the-defense-one-person-once)
- [Part B: See the defense work with a harmless test (everyone)](#part-b-see-the-defense-work-with-a-harmless-test-everyone)
- [Part C: The CTF 7 check (Person A)](#part-c-the-ctf-7-check-person-a)
- [Part D: Run the automated tests (optional)](#part-d-run-the-automated-tests-optional)
- [Undo everything](#undo-everything)
- [Troubleshooting](#troubleshooting)

---

## The idea in one minute

AIGoat's shop assistant answers questions using a **knowledge base**: a library of documents it reads before replying. Some documents come from the shop (trusted). Anyone with an account can add more (untrusted). The assistant treats both the same, so a visitor can slip in a fake "official policy" and the assistant will repeat it as fact. That is AIGoat challenge **CTF 7, "Authoritative Context Poisoning"**.

Our defense works like a librarian who checks every book's origin before handing it to the assistant:

| Piece | Plain-language job |
| --- | --- |
| **Trust gate** | Before the assistant reads anything, removes documents that visitors added. Only shop documents get through. |
| **CTF chat fix** | AIGoat's challenge chat ignored the defense settings entirely. Now it obeys them, so we can show the defense on the real challenge. |
| **Write guard** | Stops visitors from labelling their own documents as "official", or editing the shop's official documents. |
| **Audit log** | Writes down every document the gate removed, and why, so we can show it on stage. |

The **defense level** switch in AIGoat's top bar controls it per account: **Level 0 = defense off**, **Level 2 = our defense on**.

[↑ Back to top](#contents)

---

## Words used in this guide

| Word | Meaning |
| --- | --- |
| **Terminal** | The text window where you type commands. On Windows, open **Ubuntu (WSL)** from the Start menu. |
| **VM** | The team's computer in Azure that runs AIGoat. |
| **`100.x.y.z`** | The VM's private address on Tailscale. Get the real one from the team lead, or run `tailscale status` and read the `aigoat-azure` row. |
| **SSH** | A way to type commands on the VM from your own terminal. After `ssh azureuser@100.x.y.z`, your commands run on the VM until you type `exit`. |
| **Tunnel** | The connection `aigoat-start.sh` keeps open so your browser can reach AIGoat at http://localhost:3000. Keep its window open. |
| **tmux** | Keeps AIGoat running on the VM after you disconnect. **Ctrl+b, then d** leaves it running in the background. |

> [!TIP]
> Copy commands exactly. Paste into the terminal with **Ctrl+Shift+V** (or right-click). Lines starting with `#` are notes and don't need typing.

[↑ Back to top](#contents)

---

## Who does what

| Role | Who | Does |
| --- | --- | --- |
| **Installer** | One person, once (the team lead, who has the project folder) | Part A |
| **Everyone** | All three | Part B, to see it work |
| **Person A** | The attack-and-evaluation owner | Part C, tonight's gate |
| **Technical teammate** | Optional | Part D |

The VM is shared. Installing once switches the defense on for everyone.

[↑ Back to top](#contents)

---

## Part A: Install the defense (one person, once)

### A1. Start AIGoat and the tunnel

In a terminal on your laptop:

```bash
~/bin/aigoat-start.sh --start-vm
```

**You should see:** `Starting VM…`, then `AIGoat is running.` (or `already running`), then `Tunnel open: browse to http://localhost:3000`.

**Leave this window open** for the rest of the session. Closing it closes the tunnel.

> [!NOTE]
> Seeing `env: 'bash\r': No such file or directory`? Run `sed -i 's/\r$//' ~/bin/aigoat-start.sh` and try again ([why](../team-setup-runbook.md#quick-start-script)).

### A2. Copy the project to the VM

Open a **second** terminal. Go to the folder that contains the `CyberAwareBU` project folder, then copy it to the VM (replace `100.x.y.z` with the real address):

```bash
cd ~/Projects                                # the folder that contains CyberAwareBU
scp -r CyberAwareBU azureuser@100.x.y.z:~/
```

**You should see:** a list of files being copied, then your prompt back. No password prompt is expected; if you get one, see [Troubleshooting](#troubleshooting).

> [!NOTE]
> This copies the version on your laptop, including changes not yet pushed to GitHub. Re-run the same command whenever the project changes.

### A3. Connect to the VM

```bash
ssh azureuser@100.x.y.z
```

**You should see:** the prompt change to `azureuser@vm-aigoat:~$`. From now on, commands run on the VM.

### A4. Check the AIGoat version

```bash
git -C ~/AIGoat log --oneline -1
```

**You should see:** a line starting with `bb3cd1b`. A different code is fine as long as the next step reports no error.

### A5. Install the defense

```bash
~/CyberAwareBU/scripts/install-overlay.sh ~/AIGoat
```

**You should see** these lines, ending with `Done`:

```
[cyberaware] Installed controls package -> app/defense/controls/cyberaware/
[cyberaware] Applied 0001-register-cyberaware.patch
[cyberaware] Applied 0002-challenge-chat-defense.patch
[cyberaware] Applied 0003-kb-write-guard.patch
[cyberaware] Defense profiles -> config/cyberaware_profiles.yml
[cyberaware] Done. Restart AIGoat to load the overlay:
```

Running it twice is safe: the second time it says `Already applied`. If you see `ERROR`, **nothing was changed**; see [Troubleshooting](#troubleshooting).

### A6. Restart AIGoat so it loads the defense

```bash
tmux attach -t aigoat          # if it says "no sessions", type: tmux new -s aigoat
cd ~/AIGoat && ./scripts/stop.sh && ./scripts/start.sh
```

**You should see:** after a minute or two, `AI Goat is running!`. Then press **Ctrl+b**, release, press **d**. AIGoat keeps running in the background.

The tunnel window from A1 reconnects by itself; refresh the browser if a page fails once.

### A7. Confirm the defense settings are in place

```bash
grep profiles_path ~/AIGoat/config/config.yml
```

**You should see:** `profiles_path: "./config/cyberaware_profiles.yml"`.

Leave the VM with `exit`. Part A is done; tell the team.

[↑ Back to top](#contents)

---

## Part B: See the defense work with a harmless test (everyone)

This uses a made-up, harmless note to show the gate removing visitor-added documents. It takes 5 minutes and is also a good visual for the demo.

1. **Open AIGoat** at http://localhost:3000 (tunnel running) and log in with your own team account.
2. **Set defense level 0:** click the defense level in the top bar and pick **Level 0**.
3. **Add a test note:** go to http://localhost:3000/knowledge-base, open the **Documents** tab and click **Add Document**. Fill in:
   - Title: `CyberAware test note`
   - Content: `Test note: the store mascot is a goat named Cracky who loves hoodies.`
   - Leave Trust tier as `user`

   Save, then click **Sync to Vector DB**. **You should see:** "Knowledge base synced successfully!".
4. **Look without the defense:** open the **Retrieval trace** tab, type `What is the store mascot?` in **Query** and click **Run**. **You should see:** the test note in the list, marked `injected`, `user` and a green **in context** tag. The assistant would read it.
5. **Turn the defense on:** set the defense level to **Level 2** in the top bar.
6. **Look again:** click **Run** once more. **You should see:**
   - `cyberaware.trust_gate` among the control names at the top
   - the test note **struck through** with a red **`cyberaware.trust_gate`** tag: the gate removed it before the assistant could read it
   - the shop's own documents (marked `seeded`, `system`) still **in context**: normal answers keep working
7. **See the record** (optional, on the VM): `tail -n 1 ~/AIGoat/logs/cyberaware-audit.jsonl`. **You should see:** one line with `"control": "cyberaware.trust_gate"`, the reason `user-injected content` and the note's title.

> [!NOTE]
> Only an admin account can delete documents. The test note is harmless and can stay; an admin can remove it from the Documents tab later.

If step 6 matches, the defense is installed and working. If not, see [Troubleshooting](#troubleshooting).

[↑ Back to top](#contents)

---

## Part C: The CTF 7 check (Person A)

This is tonight's gate in the [prototype plan](PROTOTYPE-PLAN.md#schedule-and-gates): the same challenge should give a flag with the defense off, and no flag with it on.

1. **Defense off:** log in with a first account, set **Level 0**, open http://localhost:3000/challenges and choose **Authoritative Context Poisoning** (300 points). Click **Start Challenge** and play it using the challenge's own **hints** in the app. Turn on the **Knowledge Base** switch in the challenge chat; the challenge needs it. **Expected:** a reply containing `FLAG: AIGOAT{…}`.
2. **Write down the result** in the team notes: the time, the account, the level and whether a flag appeared.
3. **Defense on:** log out and log in with a **different** account (a won flag keeps showing for the rest of that account's attempt). Set **Level 2**, start the same challenge, turn on **Knowledge Base**, and ask the same question. **Expected:** an ordinary answer based on the shop's real information, and **no flag**.
4. **Check the record** on the VM: `tail -n 3 ~/AIGoat/logs/cyberaware-audit.jsonl` shows a `cyberaware.trust_gate` line for that moment.
5. **Repeat** steps 1 and 3 two more times each. The model's answers vary, so one run isn't proof. Record each run.

**Gate passed** when every Level 2 run gives no flag and the audit log shows the gate removing the planted document. Update the [status table](PROTOTYPE-PLAN.md#status-at-a-glance) with the result.

> [!TIP]
> Replies take 10–30 seconds on this VM. Wait for the answer before sending anything else.

[↑ Back to top](#contents)

---

## Part D: Run the automated tests (optional)

For a teammate comfortable with Python. The 21 tests check the gate, the CTF chat fix, the write guard and the settings file in about a second, without the AI model. Run them on the VM after Part A:

```bash
cd ~/CyberAwareBU
python3.11 -m venv ~/cyberaware-venv
~/cyberaware-venv/bin/pip install -q pytest pyyaml pydantic fastapi "sqlalchemy[asyncio]" aiosqlite httpx "python-jose[cryptography]" "passlib[bcrypt]" python-multipart
AIGOAT_DIR=~/AIGoat ~/cyberaware-venv/bin/python -m pytest tests/ -q
```

**You should see:** `21 passed`.

[↑ Back to top](#contents)

---

## Undo everything

To return AIGoat to its original state (for example, to measure stock behaviour), connect to the VM and run:

```bash
~/CyberAwareBU/scripts/install-overlay.sh --uninstall ~/AIGoat
```

Then restart AIGoat as in [A6](#a6-restart-aigoat-so-it-loads-the-defense). Run [A5](#a5-install-the-defense) to switch the defense back on.

[↑ Back to top](#contents)

---

## Troubleshooting

| What you see | What it means | What to do |
| --- | --- | --- |
| `env: 'bash\r': No such file or directory` | The script has Windows line endings | `sed -i 's/\r$//' ~/bin/aigoat-start.sh`, then run it again |
| `scp` or `ssh` asks for a password, or says `Permission denied (publickey)` | Your key isn't set up on the VM | See [SSH permission denied](../team-setup-runbook.md#ssh-permission-denied) in the runbook |
| `ssh` or `scp` hangs, then times out | The VM is off, or Tailscale isn't connected | Run `~/bin/aigoat-start.sh --start-vm` again; check `tailscale status` |
| `ERROR: 000X-….patch does not apply cleanly. Nothing was changed.` | AIGoat on the VM differs from the version our patches expect | Ask the team lead; usually fixed with `git -C ~/AIGoat checkout bb3cd1bbd1e0`, then A5 again |
| `ERROR: … does not look like an AIGoat checkout` | Wrong folder | Use `~/AIGoat` exactly as written |
| Browser shows "can't connect" | The tunnel window was closed | Re-run step A1 and keep that window open |
| In Part B, no `cyberaware.trust_gate` tag at Level 2 | AIGoat wasn't restarted, or the level didn't change | Repeat A6, then refresh the page and check the top bar shows Level 2 |
| Level 2 shows an error, or `logs/backend.log` mentions `defense profiles` with an error | The defense settings file didn't load | On the VM: `grep -i "defense profiles" ~/AIGoat/logs/backend.log`. A healthy line reads `Loaded … defense profiles from …/cyberaware_profiles.yml`. Send any error to the team lead |
| A flag still appears at Level 2 | The defense didn't apply to that request | Check the account really shows Level 2 and that you used a fresh account; send the time and account to the team lead |
| A lab about faking "trust tier" labels no longer works | Expected: the write guard blocks it on purpose | For that lab only, start AIGoat with `CYBERAWARE_KB_WRITE_GUARD=0` |

[↑ Back to top](#contents)
