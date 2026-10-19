# AIGoat on Azure: Team Setup Runbook

Oct 18, 2026 · @Basile Mb.

## Overview

Run AIGoat on one Azure VM that only your team can reach, through Tailscale, with a nightly auto-shutdown. Your subscription has no GPU quota, so this runbook uses a CPU-only VM: chat replies take roughly 10-30 seconds and teammates' requests queue behind each other, but every lab and challenge still works. A GPU can be added later (see the section after Step 1).

| Item | Choice |
| --- | --- |
| Region | Canada Central (fall back to another region if the VM size is unavailable) |
| VM size | Standard\_D8as\_v5: 8 vCPU (AMD), 32 GB RAM, no GPU. Use Standard\_D4as\_v5 (4 vCPU, 16 GB) if your quota is limited to 4 vCPUs |
| OS and disk | Ubuntu Server 24.04 LTS, 64 GB StandardSSD |
| Access | Tailscale only; no inbound rules left open on the Azure firewall |
| Cost guard | Auto-shutdown, budget alert, delete the resource group when finished |
| App | AIGoat via `./scripts/start.sh` (Ollama + Mistral running on CPU) |

Before you start, have these ready:

- An Azure subscription with credits and Contributor (or Owner) rights
- Azure CLI installed on your laptop or WSL (Step 0 shows how) (`az --version`), signed in with `az login`
- A Tailscale account; teammates will each need one too (check the current free-plan user limit)
- About one hour, plus any wait for quota approval

Scope rule: attack only the AIGoat app running on your own VM. Do not point scanners or fuzzers at anything else from this VM, and no denial-of-service testing. This follows Microsoft's penetration testing rules of engagement; read them once before you begin.

## Step 0: Install the Azure CLI (Ubuntu or WSL)

Every `az` command in this runbook needs the Azure CLI. On Ubuntu, including WSL 2, Microsoft's install script sets it up in one command:

```bash
curl -sL https://aka.ms/InstallAzureCLIDeb | sudo bash   # Microsoft's official installer for Debian and Ubuntu
az --version                                             # confirm it installed
az login                                                 # opens a browser to sign in
```

The installer runs as administrator. If you would rather read it first, download it with `curl -sL https://aka.ms/InstallAzureCLIDeb -o install.sh`, open it with `less install.sh`, then run `sudo bash install.sh`. On WSL, if `az login` does not open a browser, use `az login --use-device-code` and enter the code at the page it prints.

## Step 1: Check credits, CPU size and quota

A CPU-only VM needs much less quota than a GPU, so this check is quick. You need 8 free vCPUs in one region (4 if you use the smaller size). Free-trial subscriptions are often capped at 4 vCPUs per region, so check this first.

1. In the portal, open Subscriptions, pick yours, and note the offer type. Under Cost Management + Billing, check the credit balance and expiry date.
2. Select the subscription and confirm the VM size exists in your region:

```bash
az login
az account set --subscription "<name or id>"
az vm list-skus --location canadacentral --size Standard_D8as_v5 --output table
```

If the output shows a restriction such as `NotAvailableForSubscription`, try another region (for example East US) and use it for every command below.

**Check your quota** for the AMD Dasv5 family and the regional total:

```bash
az vm list-usage --location canadacentral --output table | grep -i -E "DASv5|Total Regional"
```

Free vCPUs are the limit minus the current usage. You need 8 free on `Standard DASv5 Family vCPUs` and on `Total Regional vCPUs`, or 4 for the smaller `Standard_D4as_v5`.

**If the limit is too low, request an increase:** portal, Subscriptions, Usage + quotas, filter on "DASv5", then request a new limit of 8. CPU quota requests are often approved within minutes. If your subscription is a free trial capped at 4 vCPUs, either use `Standard_D4as_v5` or upgrade to pay-as-you-go (remaining credits normally carry over).

**You do not need a GPU for this runbook.** If D-series sizes are restricted in Canada Central, use `Standard_D8s_v5` (Intel) instead and change the size in Step 3. If you want faster replies later, see the next section.

### If you want a GPU later

A GPU brings replies down to 1-3 seconds, but nothing in this runbook requires one. Options, best first:

| Option | Reply speed | Cost | Catch |
| --- | --- | --- | --- |
| Upgrade to pay-as-you-go, then request A10 quota (`Standard NVADSA10v5 Family`, for example `Standard_NV18ads_A10_v5`, in Central US) | 1-3 s | Credits | Recreate the network in the new region; needs NVIDIA's GRID driver; confirm Ollama uses the GPU slice |
| Run AIGoat on Google Colab (documented in `colab_notebooks/AIGoat_Colab.md` in the repo) | 1-3 s | Free tier | Sessions time out and reset; each teammate runs their own notebook |
| Each teammate runs it locally on an Apple Silicon Mac or an NVIDIA laptop | 1-3 s | Free | Needs 16 GB+ RAM; the setup is repeated on each machine |
| Proxmox VM, CPU only | 10-30 s | Free | Same speed as this Azure VM without using credits; set the CPU type to `host` |

CPU reply speed depends on core count and AVX2 support. A smaller model such as `tinyllama` (set `ollama.model` in `config/config.yml`) is much faster, but exploits that work on Mistral may behave differently on it.

On a free-trial subscription, GPU families are normally blocked until you upgrade to pay-as-you-go. Remaining credits usually carry over.

## Step 2: Create the resource group and a locked-down network

Put everything in one resource group so a single delete removes it all later. Run these from your laptop terminal, not Azure Cloud Shell, because the SSH rule below uses your laptop's public IP.

```bash
RG=rg-aigoat
LOC=canadacentral
VM=vm-aigoat

az group create -n $RG -l $LOC

az network vnet create -g $RG -n vnet-aigoat \
  --address-prefixes 10.20.0.0/16 \
  --subnet-name snet-vm --subnet-prefixes 10.20.1.0/24

az network nsg create -g $RG -n nsg-aigoat
```

**Add one temporary SSH rule**, limited to your own IP. It is used only for first-time setup and is deleted in Step 5:

```bash
MYIP=$(curl -s https://ifconfig.me)
az network nsg rule create -g $RG --nsg-name nsg-aigoat \
  -n AllowInboundSSH --priority 100 --access Allow \
  --direction Inbound --protocol Tcp \
  --destination-port-ranges 22 --source-address-prefixes $MYIP/32
```

Azure's default rules already block all other inbound traffic from the internet, and you will not open ports 3000 or 8000 at all.

**Set a budget alert** in the portal: Cost Management, Budgets, Add. Scope it to `rg-aigoat` and add alerts at 50%, 80% and 100%. Budgets track spend, not your credit balance, so also check the credit balance under Cost Management + Billing once a week.

## Step 3: Create the VM and set auto-shutdown

```bash
az vm create -g $RG -n $VM \
  --image Canonical:ubuntu-24_04-lts:server:latest \
  --size Standard_D8as_v5 \
  --admin-username azureuser --generate-ssh-keys \
  --os-disk-size-gb 64 --storage-sku StandardSSD_LRS \
  --vnet-name vnet-aigoat --subnet snet-vm \
  --nsg nsg-aigoat --public-ip-sku Standard \
  --security-type Standard

az vm auto-shutdown -g $RG -n $VM --time 0300
```

Why these choices:

- `--security-type Standard` avoids Secure Boot problems if you add a GPU driver later.
- The VM keeps a public IP only so it can reach the internet for downloads. With the SSH rule removed in Step 5, nothing can connect in from outside.
- Auto-shutdown time is in UTC: `0300` is 11 pm EDT or 10 pm EST. Shutdown deallocates the VM, which stops compute billing.
- Your SSH key is saved under `~/.ssh` on the machine where you ran the command. Back it up; losing it means losing admin access.

Copy the `publicIpAddress` from the command output, then connect:

```bash
ssh azureuser@<publicIpAddress>
```

Check the monthly cost estimate for this size in the Azure pricing calculator and compare it to your remaining credits before leaving the VM running for days.

## Step 4: Update the VM and check its CPU

A CPU-only VM needs no GPU driver. Update the system and reboot:

```bash
sudo apt update && sudo apt -y upgrade
sudo reboot
```

Reconnect after about a minute and confirm the CPU has the fast instruction sets Ollama relies on:

```bash
lscpu | grep -o -E 'avx2|avx512f' | sort -u
nproc
free -h
```

You should see `avx2`, 8 CPUs and about 31 GB of memory (4 CPUs and about 15 GB on the smaller size). If `avx2` is missing, replies will be far slower than expected; pick a different size.

- If you get GPU quota later, resize the VM to a GPU size, install the NVIDIA driver (`sudo ubuntu-drivers install` on NC-series; NVIDIA's GRID driver on NV A10 v5 sizes), reboot and run `nvidia-smi`.
- Then restart Ollama with `sudo systemctl restart ollama`. `ollama ps` should show `GPU` instead of `CPU`.

Every other step in this runbook is the same for CPU and GPU VMs.

## Step 5: Add Tailscale and close public access

Tailscale gives the VM a private address that only your team's devices can reach, so no inbound port needs to be open on Azure.

**Install and join the VM to your tailnet (run on the VM, after you connect with SSH):**

```bash
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up --hostname=aigoat-azure
tailscale ip -4
```

Open the login URL it prints and approve the device. Note the `100.x.y.z` address from the last command.

**In the Tailscale admin console:**

- Disable key expiry for this machine so it does not drop off the network after a few months.
- Invite your two teammates to the tailnet, or share the machine with their Tailscale accounts. Each of them installs Tailscale on their laptop and signs in.

**Give teammates SSH access.** Each person prints their public key in their own terminal and sends you the one line it outputs:

```bash
cat ~/id_ed25519.pub
```

Copy the whole line, which starts with `ssh-ed25519`. In this setup the key sits in your home folder (`~/id_ed25519.pub`), not inside `~/.ssh`, so the path has no `.ssh` in it. The key is printed to the screen, so copy it from the terminal. Never send the private key (`id_ed25519`, the file without `.pub`). If the file does not exist, run `ssh-keygen -t ed25519`, and use `ls ~/*.pub ~/.ssh/*.pub` to see which keys you have.

SSH only looks in `~/.ssh` by default. If your private key is also in the home folder, either move it with `mv ~/id_ed25519 ~/.ssh/ && chmod 600 ~/.ssh/id_ed25519`, or connect with `ssh -i ~/id_ed25519 azureuser@100.x.y.z`.

Append each teammate's line to `/home/azureuser/.ssh/authorized_keys` with Azure Run Command, run from your laptop. It works even when SSH is not working yet:

```bash
az vm run-command invoke -g rg-aigoat -n vm-aigoat --command-id RunShellScript --scripts "echo 'ssh-ed25519 AAAA...paste-key-here teammate' >> /home/azureuser/.ssh/authorized_keys"
```

`>>` appends. A single `>` would overwrite the file and lock you out. This is one shared Linux account, which is fine for a three-person lab.

**Join your laptop to the tailnet (WSL 2).** Your SSH key and the Azure CLI live in WSL, so WSL needs its own Tailscale connection, even if Tailscale for Windows is also installed. First check that systemd is running:

```bash
ps -p 1 -o comm=
```

If it prints `init` instead of `systemd`, enable it, then run `wsl --shutdown` in PowerShell and reopen WSL:

```bash
sudo tee /etc/wsl.conf <<'EOF'
[boot]
systemd=true
EOF
```

Install Tailscale and sign in with the same account as the VM:

```bash
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up --hostname=laptop-wsl
```

Then check that WSL can see the VM:

```bash
tailscale status
tailscale ping 100.x.y.z
```

Use the VM's `100.x.y.z` address with SSH rather than the `aigoat-azure` name, because WSL often does not resolve Tailscale names.

**Install Tailscale on your main computer (optional).** The port forward through WSL is enough to use AIGoat, so this is only needed if you want Windows apps, or teammates who are not using WSL, to reach the VM directly, for example for SSH or file copies. It does not make browser login work on the `100.x.y.z` address (see Step 7). Sign in with the same Tailscale account as the VM.

**Windows.** Run in PowerShell, or download the installer from tailscale.com/download/windows. Then sign in from the Tailscale icon in the system tray:

```powershell
winget install --id Tailscale.Tailscale
```

**Mac.** Install Tailscale from the Mac App Store, or download it from tailscale.com/download/mac. Then sign in from the menu bar icon.

**Linux** (not WSL; the same commands as on the VM):

```bash
curl -fsSL https://tailscale.com/install.sh | sh   # install Tailscale
sudo tailscale up                                   # prints a login URL; open it and approve
```

Check that it works. On Windows, run this in PowerShell; on Mac and Linux, use any terminal:

```bash
tailscale status
```

The VM should appear in the list. WSL and Windows show up as two separate devices on your tailnet, which is fine; keep both.

**Test from WSL over Tailscale** before removing the public rule:

```bash
ssh azureuser@100.x.y.z
```

**Keep Tailscale SSH off.** This runbook uses regular key-based SSH. If you ran `tailscale set --ssh` earlier, Tailscale answers SSH itself and your keys stop working. Turn it off from your laptop:

```bash
az vm run-command invoke -g rg-aigoat -n vm-aigoat --command-id RunShellScript --scripts "tailscale set --ssh=false"
```

**If you see `Permission denied (publickey)`.** The network path works, but the VM rejected your key. Two common causes: SSH only offers keys from `~/.ssh` (yours may sit in the home folder), and `az vm create --generate-ssh-keys` installs a different key (usually `~/.ssh/id_rsa`) than your ed25519 one.

First, try the key Azure generated:

```bash
ls ~/.ssh
ssh -i ~/.ssh/id_rsa azureuser@100.x.y.z
```

If that fails, add your ed25519 public key to the VM. This works without SSH:

```bash
PUB=$(cat ~/id_ed25519.pub)
az vm run-command invoke -g rg-aigoat -n vm-aigoat --command-id RunShellScript --scripts "echo '$PUB' >> /home/azureuser/.ssh/authorized_keys"
```

Then connect and name the key explicitly:

```bash
chmod 600 ~/id_ed25519
ssh -i ~/id_ed25519 azureuser@100.x.y.z
```

If SSH says the key permissions are too open, the file is probably on a Windows drive (a path under `/mnt/c`). Copy it into WSL's own filesystem. After that, plain `ssh azureuser@100.x.y.z` works without `-i`:

```bash
mkdir -p ~/.ssh && cp ~/id_ed25519 ~/id_ed25519.pub ~/.ssh/ && chmod 600 ~/.ssh/id_ed25519
```

To see which key SSH offers and what the server accepts:

```bash
ssh -v -i ~/id_ed25519 azureuser@100.x.y.z 2>&1 | grep -E "Offering|Authentications|identity file"
```

**Remove the temporary public SSH rule** (run on your laptop):

```bash
az network nsg rule delete -g $RG --nsg-name nsg-aigoat -n AllowInboundSSH
```

Verify: `ssh azureuser@<publicIpAddress>` should now time out, while the Tailscale address still works.

**Optional host firewall (UFW).** Run this on the VM, only after the Tailscale SSH test passes. It is a second layer behind the Azure firewall: it drops any incoming traffic that does not arrive through Tailscale. Keep the order, so you do not lock yourself out:

```bash
sudo ufw default deny incoming    # block all incoming traffic by default
sudo ufw default allow outgoing   # let the VM reach the internet (apt, git, Ollama downloads)
sudo ufw allow in on tailscale0   # exception: allow anything arriving over the Tailscale interface
sudo ufw enable                   # turn the firewall on (answer y if it warns about SSH)
```

`allow in on tailscale0` permits incoming connections only on the `tailscale0` interface, which Tailscale creates for traffic from your tailnet. SSH (port 22), the app (3000) and the API (8000) are then reachable only from devices on your tailnet. Running `sudo ufw enable` before that rule would cut off your own SSH session, which is why the order matters. UFW warns that enabling may disrupt SSH; answering `y` is safe once the Tailscale rule is in place.

Check the result:

```bash
sudo ufw status verbose           # expect: Default: deny (incoming), allow (outgoing), and a rule for tailscale0
```

If you lock yourself out, turn the firewall off without SSH from your laptop:

```bash
az vm run-command invoke -g rg-aigoat -n vm-aigoat --command-id RunShellScript --scripts "ufw disable"
```

## Step 6: Install Ollama and deploy AIGoat

AIGoat's start script requires **Python 3.11** and stops with `[FAIL] Python 3.11 is required (CI pin / pyproject target-version)` if it finds anything else. Ubuntu 24.04 ships Python 3.12, so install 3.11 alongside it and leave the project's `target-version` alone. The stock Node 18 package is enough. Run on the VM, over Tailscale:

```bash
sudo apt -y install git tmux curl software-properties-common nodejs npm
sudo add-apt-repository -y ppa:deadsnakes/ppa   # source for extra Python versions on Ubuntu
sudo apt update
sudo apt -y install python3.11 python3.11-venv python3.11-dev
python3.11 --version                            # should print 3.11.x
node -v                                         # needs 18 or newer
```

**Install Ollama and pull the model:**

```bash
curl -fsSL https://ollama.com/install.sh | sh
ollama pull mistral
ollama run mistral "Say hello in five words"
ollama ps
```

`ollama ps` will show `100% CPU` on this VM, which is expected. The first reply after a long idle period is the slowest because the model has to load. Replies stay in the 10-30 second range, and requests from teammates queue behind each other.

**Clone and start AIGoat inside tmux**, so it keeps running when your SSH session closes:

```bash
git clone https://github.com/AISecurityConsortium/AIGoat.git
cd AIGoat
chmod +x scripts/*.sh
tmux new -s aigoat
python3.11 -m venv ~/aigoat-venv     # a Python 3.11 environment
source ~/aigoat-venv/bin/activate    # makes python and python3 mean 3.11 in this shell
python --version                     # confirm it prints 3.11.x
./scripts/start.sh
```

Activate the environment inside tmux, and again in any new tmux window or after reattaching to a new shell. If the script still reports the wrong version, see how it picks Python with `grep -n -i python scripts/start.sh`.

The first run installs Python and npm dependencies, so allow several minutes. Wait for "AI Goat is running!". Detach with Ctrl+b then d, and reattach later with `tmux attach -t aigoat`.

The start script is documented to check Ollama, pull Mistral if missing, initialize the database and start both servers. I have not run it on this exact VM image, so if it fails, check the log output and the project's troubleshooting notes.

**Optional agent model.** On startup the script may warn that the tool-calling model `qwen3.5:9b` is not installed. The agent, MCP host and kill chain labs make no tool calls without it, but the other labs run on Mistral. To install it, run `ollama pull qwen3.5:9b` (a multi-gigabyte download that needs more RAM and will be slow on a CPU-only VM), or start with `AIGOAT_PULL_AGENT_MODEL=1 ./scripts/start.sh`. Skip it until you need those labs.

## Step 7: Reach the app from team laptops and smoke-test

Each teammate connects to Tailscale, forwards both app ports over SSH, and opens the app at `http://localhost:3000`. This is the supported way in: the frontend (port 3000) calls the backend (port 8000) from the browser, and the backend only accepts those browser requests from the `localhost` origin. Opening the app by its `100.x.y.z` address loads the pages, but login fails (see below).

```bash
ssh -L 3000:localhost:3000 -L 8000:localhost:8000 azureuser@100.x.y.z
```

If your key is not in `~/.ssh`, add `-i ~/id_ed25519` to this command.

Keep that session open and browse to http://localhost:3000 (API docs at http://localhost:8000/docs).

**Do not use the Tailscale address in the browser.** Opening `http://100.x.y.z:3000` loads the pages, but login fails: the browser's preflight request (`OPTIONS /api/auth/login/`) comes from that origin and the backend answers `400 Bad Request`, which shows up in `logs/backend.log`. The `localhost:3000` tunnel works because requests then come from the `localhost` origin. If you need direct access later, allow that origin in the backend's CORS settings; find them with `grep -rn -i -E "cors|allow_origins" ~/AIGoat/app ~/AIGoat/config`.

**WSL users:** your Windows browser cannot use the Tailscale connection inside WSL, and the direct `100.x.y.z` address does not work for login anyway. Use the port forward above and browse `http://localhost:3000`.

**Smoke test**, to run once with the whole team:

- Log in as one of the preset users (no sign-up needed; alice, bob, charlie and frank all use password123). Give each teammate their own user so chats and CTF progress stay separate, for example `alice` / `password123` (admin is `admin` / `admin123`).
- Send a chat message and time the reply. Expect 10-30 seconds on CPU. If it takes over a minute, check `htop` and `free -h` on the VM.
- Open an Attack Lab and a CTF challenge, and confirm the defense-level toggle in the navigation bar works.
- **Test for shared state.** Have two people log in at once. One adds a Knowledge Base entry and syncs it to the vector database; check whether the other person's chatbot is affected, and whether switching defense level changes it for both. Also have two people send a message at the same moment to see how long the second one waits. If it interferes, agree on who works on which lab at a time.

**If login fails ("Invalid credentials" for every user).** First check how you opened the app. Open it at `http://localhost:3000` through the port forward, not the `100.x.y.z` address. Through the Tailscale address the pages load, but the backend answers the browser's preflight check (`OPTIONS /api/auth/login/`) with `400 Bad Request`, so the login never goes through and the page shows a generic failure. You can see those lines with `tail -n 30 ~/AIGoat/logs/backend.log`. After switching to the localhost address, use a private window or a hard refresh (Ctrl+Shift+R). Only if the backend log shows the login `POST` itself failing (for example a 401) is the database the problem. In that case, reseed using the backend's own Python environment, because the seed script needs the same libraries as the app. Find the interpreter the running backend uses:

```bash
PID=$(ss -tlnp | grep ':8000' | grep -o 'pid=[0-9]*' | cut -d= -f2)
tr '\0' ' ' < /proc/$PID/cmdline; echo    # prints something like /home/azureuser/AIGoat/venv/bin/python3 ...
```

Then stop the app, seed with that interpreter (replace `<PYTHON>` with the path printed above), and start it again:

```bash
cd ~/AIGoat
./scripts/stop.sh
<PYTHON> -m scripts.seed     # should end with: Seed completed successfully.
./scripts/start.sh
```

If nothing is listening on port 8000, install the dependencies into your venv and seed with it:

```bash
cd ~/AIGoat
source ~/aigoat-venv/bin/activate
pip install -r requirements.txt
python -m scripts.seed
```

**Seed script cautions**

- A full run resets the passwords of the five preset users (`alice`, `bob`, `charlie`, `frank`, `admin`) and recreates the shop data.
- A full run also deletes every CTF challenge attempt. Once teammates have solved challenges, use `python -m scripts.seed --sync-challenges` instead, which updates the challenge text and keeps the attempts.
- Each full run adds another 6-8 random orders per demo user. To refresh only the support tickets, use `python -m scripts.seed --sync-support`.
- Run it from `~/AIGoat`, so it writes to the same database the backend reads.

**Confirmed on this setup:** the backend runs from the environment the start script builds at `~/AIGoat/venv`. The simplest reseed is therefore:

```bash
cd ~/AIGoat
./scripts/stop.sh
source ~/AIGoat/venv/bin/activate
python -c "import sqlalchemy; print(sqlalchemy.__version__)"   # must print a version, not an error
python -m scripts.seed                                          # should end with: Seed completed successfully.
./scripts/start.sh
```

The start script reported `Database already has required data` after the reseed, so if login still fails at this point, the cause is the browser calling the wrong address, not the database. Check the request URL in DevTools as described above.

## Step 8: Day-to-day operation, cost control and teardown

The VM bills for compute, disk and the public IP while allocated. Use deallocate, not just an operating-system shutdown, because a merely stopped VM still bills for compute.

**Start and stop** (from any laptop with Azure CLI):

```bash
az vm start -g rg-aigoat -n vm-aigoat
az vm deallocate -g rg-aigoat -n vm-aigoat
az vm list -g rg-aigoat -d -o table
```

The last command should show the power state `VM deallocated` when you are done. The Tailscale address stays the same across restarts.

**After every start**, SSH in, run `tmux new -s aigoat`, then `cd AIGoat && ./scripts/start.sh`. Ollama starts on its own as a service, and the model stays on disk.

**Take a baseline snapshot** once the smoke test passes, so you can roll back after heavy experiments. Snapshots are cheap but not free:

```bash
OSDISK=$(az vm show -g rg-aigoat -n vm-aigoat --query storageProfile.osDisk.managedDisk.id -o tsv)
az snapshot create -g rg-aigoat -n snap-aigoat-baseline --source $OSDISK
```

**Team rules**

- Tell the others before running `./scripts/stop.sh --clean && ./scripts/start.sh`; it resets the database for everyone.
- Attack only the AIGoat app on this VM. No scanning or fuzzing of other targets, and no network flooding. The Unbounded Consumption lab (token flooding the model) is fine, since it stays on your own VM.
- Never open ports 3000 or 8000 to the internet, and never add a public inbound rule.
- Whoever finishes last confirms the VM is deallocated.

**Teardown** when the project is over. This deletes the VM, disk, snapshot, network and IP together:

```bash
az group delete -n rg-aigoat --yes --no-wait
```

Then remove the `aigoat-azure` machine from the Tailscale admin console.

## Step 9: Stop, start and come back to the app

There are two layers: the app (processes running on the VM) and the VM itself (what Azure bills for). Stopping the app does not stop the billing; deallocating the VM does.

**Stop the app** (the VM stays on):

```bash
cd ~/AIGoat
./scripts/stop.sh        # stops the frontend and backend; Ollama keeps running as a system service
```

**Start the app inside tmux**, so it keeps running when your SSH session closes:

```bash
tmux new -s aigoat       # use `tmux attach -t aigoat` instead if the session already exists
cd ~/AIGoat
./scripts/start.sh       # wait for "AI Goat is running!"
```

The start script builds and uses its own environment at `~/AIGoat/venv`, so you do not need to activate anything first. If it reports the wrong Python version, install Python 3.11 as in Step 6. To leave the app running and get your terminal back, press Ctrl+b, then d.

**Check that it is running:**

```bash
ss -tlnp | grep -E '3000|8000'     # both ports should be listening
tail -n 20 ~/AIGoat/logs/backend.log
```

**Come back later.** Pick the row that matches what happened:

| Situation | What to do |
| --- | --- |
| Your SSH session dropped but the VM is still on | SSH back in and run `tmux attach -t aigoat`; the app kept running |
| The VM was deallocated (auto-shutdown at 0300 UTC, or you stopped it) | Run `az vm start -g rg-aigoat -n vm-aigoat` from your laptop and wait a minute. Tailscale reconnects by itself. SSH in, then start the app again with the tmux commands above, because tmux sessions and the running app do not survive a shutdown |
| The browser says it cannot connect | The SSH tunnel on your laptop is closed. Run the `ssh -L` command from Step 7 again and keep that terminal open |
| You want a clean database | Tell the team first, then run `./scripts/stop.sh --clean && ./scripts/start.sh`. This resets everyone |

**Useful tmux commands:** `tmux ls` lists sessions, `tmux attach -t aigoat` rejoins one, and `tmux kill-session -t aigoat` removes it. Detach without stopping the app with Ctrl+b, then d.

**When you are done for the day,** stop the app if you like, then deallocate the VM from your laptop so billing stops:

```bash
az vm deallocate -g rg-aigoat -n vm-aigoat
az vm list -g rg-aigoat -d -o table    # PowerState should read: VM deallocated
```

## Troubleshooting

| Symptom | Likely cause | Fix |
| --- | --- | --- |
| `QuotaExceeded` or `OperationNotAllowed` creating the VM | Not enough free vCPUs in the region | Request more DASv5 and regional vCPUs, or use `Standard_D4as_v5` (Step 1) |
| `SkuNotAvailable` | Size restricted or out of capacity in that region | Try `Standard_D8s_v5`, or recreate the resource group and network in another region |
| `[FAIL] Python 3.11 is required` from start.sh | Ubuntu 24.04 ships Python 3.12 | Install 3.11 from the deadsnakes PPA and activate a 3.11 venv before running the script (Step 6); do not change `target-version` |
| Chat takes 10-30 seconds | Expected on CPU | Use `tinyllama` for the easier labs, add vCPUs, or add a GPU later |
| Chat takes over a minute or times out | Several people prompting at once, or too little RAM | One person per lab at a time; check `free -h` and `htop` |
| `lscpu` shows no `avx2` | Unsuitable VM size | Resize to a Dasv5 or Dsv5 size |
| start.sh says Ollama not reachable | Ollama service not running | `sudo systemctl status ollama`, then `sudo systemctl start ollama` |
| `ssh` to the `100.x.y.z` address fails or times out | WSL is not on the tailnet, the VM is deallocated, or the key expired | Install Tailscale inside WSL (Step 5); `az vm start`; check `tailscale status` and key expiry in the admin console |
| `Permission denied (publickey)` | Your public key is not in `authorized_keys`, or Tailscale SSH is on | Make sure SSH offers the right key (use -i \~/id\_ed25519, or move the key into \~/.ssh), add it with Azure Run Command, and turn Tailscale SSH off (Step 5) |
| Pages load but login or chat fails in the browser | App was opened by its 100.x.y.z address; the backend rejects that origin (the CORS preflight returns 400 in logs/backend.log) | Forward ports 3000 and 8000 over SSH and open http://localhost:3000 (Step 7) |
| Port already in use | Previous run still alive | `./scripts/stop.sh`, then start again |
| Still being charged after "stopping" | VM stopped but not deallocated | `az vm deallocate`; confirm with `az vm list -d` |
