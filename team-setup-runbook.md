# AIGoat on Azure: Team Setup Runbook

## Overview

This runbook deploys AIGoat on a single Azure VM that is reachable only by your team over Tailscale, with no inbound ports exposed to the internet and a nightly auto-shutdown to control cost. It targets a CPU-only VM, which works on subscriptions without GPU quota: chat replies take roughly 10-30 seconds and concurrent requests queue, but every lab and challenge works. GPU options are covered after Step 1.

| Item | Choice |
| --- | --- |
| Region | Any region where the VM size is available to your subscription |
| VM size | Standard\_D8as\_v5: 8 vCPU (AMD), 32 GB RAM, no GPU. Use Standard\_D4as\_v5 (4 vCPU, 16 GB) if quota is limited to 4 vCPUs |
| OS and disk | Ubuntu Server 24.04 LTS, 64 GB StandardSSD |
| Access | Tailscale only; no inbound rules left open on the Azure NSG |
| Cost guard | Auto-shutdown, budget alert, resource group deletion at teardown |
| App | AIGoat via `./scripts/start.sh` (Ollama + Mistral on CPU) |

Prerequisites:

- An Azure subscription with credits and Contributor (or Owner) rights
- Azure CLI on your workstation or WSL (Step 0), signed in with `az login`
- A Tailscale account for each team member (check the current free-plan user limit)
- About one hour, plus any wait for quota approval

Scope rule: attack only the AIGoat instance running on your own VM. Do not point scanners or fuzzers at any other target from this VM, and do not perform denial-of-service testing. This follows Microsoft's penetration testing rules of engagement; review them before starting.

### Conventions

The commands below use these shell variables. Set them once per terminal session on your workstation:

```bash
RG=rg-aigoat
LOC=<region>        # for example eastus, westeurope, canadacentral
VM=vm-aigoat
```

`100.x.y.z` stands for the VM's Tailscale IPv4 address, and `<publicIpAddress>` for its Azure public IP.

## Step 0: Install the Azure CLI (Ubuntu or WSL)

On Ubuntu, including WSL 2, Microsoft's install script sets up the CLI in one command:

```bash
curl -sL https://aka.ms/InstallAzureCLIDeb | sudo bash   # Microsoft's official installer for Debian and Ubuntu
az --version                                             # confirm the install
az login                                                 # opens a browser to sign in
```

The installer runs as root. To review it first, download it with `curl -sL https://aka.ms/InstallAzureCLIDeb -o install.sh`, inspect it with `less install.sh`, then run `sudo bash install.sh`. On WSL, if `az login` does not open a browser, use `az login --use-device-code`.

## Step 1: Check credits, VM size and quota

You need 8 free vCPUs in one region (4 for the smaller size). Free-trial subscriptions are often capped at 4 vCPUs per region.

1. In the portal, open Subscriptions and note the offer type. Under Cost Management + Billing, check the credit balance and expiry date.
2. Select the subscription and confirm the VM size is offered in your region:

```bash
az account set --subscription "<name or id>"
az vm list-skus --location $LOC --size Standard_D8as_v5 --output table
```

If the output shows a restriction such as `NotAvailableForSubscription`, choose another region and update `LOC`.

**Check quota** for the AMD Dasv5 family and the regional total:

```bash
az vm list-usage --location $LOC --output table | grep -i -E "DASv5|Total Regional"
```

Free vCPUs equal the limit minus current usage. You need 8 free on both `Standard DASv5 Family vCPUs` and `Total Regional vCPUs` (4 for `Standard_D4as_v5`).

**If the limit is too low, request an increase:** portal, Subscriptions, Usage + quotas, filter on "DASv5", and request a new limit of 8. CPU quota requests are usually approved within minutes. On a free trial capped at 4 vCPUs, either use `Standard_D4as_v5` or upgrade to pay-as-you-go (remaining credits normally carry over).

If Dasv5 sizes are restricted in your region, use `Standard_D8s_v5` (Intel) and change the size in Step 3.

### Optional: GPU acceleration

A GPU brings replies down to 1-3 seconds, but nothing in this runbook requires one.

| Option | Reply speed | Cost | Considerations |
| --- | --- | --- | --- |
| Pay-as-you-go subscription with A10 quota (`Standard NVADSA10v5 Family`, for example `Standard_NV18ads_A10_v5`) | 1-3 s | Credits | Region availability varies; requires NVIDIA's GRID driver; confirm Ollama uses the GPU slice |
| Google Colab (see `colab_notebooks/AIGoat_Colab.md` in the repo) | 1-3 s | Free tier | Sessions time out and reset; each user runs their own notebook |
| Local install on Apple Silicon or an NVIDIA laptop | 1-3 s | Free | Needs 16 GB+ RAM; setup is repeated per machine |
| On-premises hypervisor VM (for example Proxmox), CPU only | 10-30 s | Free | Same speed as this VM without cloud spend; set the CPU type to `host` |

CPU reply speed depends on core count and AVX2 support. A smaller model such as `tinyllama` (set `ollama.model` in `config/config.yml`) is much faster, but exploits that work on Mistral may behave differently.

GPU families are normally blocked on free-trial subscriptions until you upgrade to pay-as-you-go.

## Step 2: Create the resource group and a locked-down network

Keep every resource in one resource group so a single delete removes everything. Run these from your workstation, not Azure Cloud Shell, because the SSH rule below uses your workstation's public IP.

```bash
az group create -n $RG -l $LOC

az network vnet create -g $RG -n vnet-aigoat \
  --address-prefixes 10.20.0.0/16 \
  --subnet-name snet-vm --subnet-prefixes 10.20.1.0/24

az network nsg create -g $RG -n nsg-aigoat
```

**Add one temporary SSH rule**, restricted to your public IP. It is used only for initial setup and removed in Step 5:

```bash
MYIP=$(curl -s https://ifconfig.me)
az network nsg rule create -g $RG --nsg-name nsg-aigoat \
  -n AllowInboundSSH --priority 100 --access Allow \
  --direction Inbound --protocol Tcp \
  --destination-port-ranges 22 --source-address-prefixes $MYIP/32
```

Azure's default NSG rules deny all other inbound internet traffic. Ports 3000 and 8000 are never opened.

**Set a budget alert** in the portal: Cost Management, Budgets, Add. Scope it to the resource group and add alerts at 50%, 80% and 100%. Budgets track spend, not credit balance, so also review the credit balance under Cost Management + Billing weekly.

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

Design notes:

- `--security-type Standard` avoids Secure Boot issues if a GPU driver is added later.
- The public IP is kept only for outbound internet access (package and model downloads). Once the SSH rule is removed in Step 5, no inbound connection is possible from outside.
- The auto-shutdown time is in UTC; convert it to a time that suits your team's working hours. Auto-shutdown deallocates the VM, which stops compute billing.
- `--generate-ssh-keys` stores the key pair under `~/.ssh` on the machine that ran the command. Back it up; losing it means losing admin access.

Copy `publicIpAddress` from the output and connect:

```bash
ssh azureuser@<publicIpAddress>
```

Check the monthly estimate for the chosen size in the Azure pricing calculator against your remaining credits before leaving the VM running for extended periods.

## Step 4: Update the VM and verify the CPU

A CPU-only VM needs no GPU driver. Update and reboot:

```bash
sudo apt update && sudo apt -y upgrade
sudo reboot
```

Reconnect after about a minute and confirm the instruction sets Ollama relies on:

```bash
lscpu | grep -o -E 'avx2|avx512f' | sort -u
nproc
free -h
```

Expected: `avx2`, 8 CPUs and about 31 GB of memory (4 CPUs and about 15 GB on the smaller size). If `avx2` is missing, inference will be much slower; choose a different size.

- If GPU quota becomes available, resize to a GPU size, install the NVIDIA driver (`sudo ubuntu-drivers install` on NC-series; NVIDIA's GRID driver on NV A10 v5 sizes), reboot and run `nvidia-smi`.
- Then restart Ollama with `sudo systemctl restart ollama`. `ollama ps` should report `GPU` instead of `CPU`.

All remaining steps are identical for CPU and GPU VMs.

## Step 5: Add Tailscale and close public access

Tailscale gives the VM a private address reachable only from devices on your tailnet, so no inbound port needs to be open on Azure.

**Install Tailscale and join the VM to the tailnet (on the VM):**

```bash
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up --hostname=aigoat-azure
tailscale ip -4
```

Open the printed login URL and approve the device. Record the `100.x.y.z` address.

**In the Tailscale admin console:**

- Disable key expiry for this machine so it does not drop off the tailnet.
- Invite team members to the tailnet, or share the machine with their Tailscale accounts. Each member installs Tailscale on their workstation and signs in.

**Grant team members SSH access.** Each member sends their public key, which is a single line beginning with `ssh-ed25519`:

```bash
cat ~/.ssh/id_ed25519.pub
```

Only the `.pub` file is shared; the private key (`id_ed25519`) never leaves its owner's machine. If no key exists, generate one with `ssh-keygen -t ed25519`. `ls ~/.ssh/*.pub` lists existing keys.

Append each key to `/home/azureuser/.ssh/authorized_keys` with Azure Run Command, which works even when SSH does not:

```bash
az vm run-command invoke -g $RG -n $VM --command-id RunShellScript --scripts "echo 'ssh-ed25519 AAAA...paste-key-here member-name' >> /home/azureuser/.ssh/authorized_keys"
```

`>>` appends; a single `>` would overwrite the file and lock everyone out. A single shared Linux account is acceptable for a small lab team; for larger teams, create one account per user.

**Join a WSL 2 workstation to the tailnet.** If your SSH key and Azure CLI live in WSL, WSL needs its own Tailscale connection, even when Tailscale for Windows is installed. First confirm systemd is running:

```bash
ps -p 1 -o comm=
```

If it prints `init` instead of `systemd`, enable it, run `wsl --shutdown` in PowerShell, and reopen WSL:

```bash
sudo tee /etc/wsl.conf <<'EOF'
[boot]
systemd=true
EOF
```

Install Tailscale and sign in with the same tailnet as the VM:

```bash
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up --hostname=workstation-wsl
```

Verify connectivity:

```bash
tailscale status
tailscale ping 100.x.y.z
```

Use the `100.x.y.z` address for SSH rather than the MagicDNS name, because WSL often does not resolve Tailscale names.

**Install Tailscale on the host OS (optional).** The SSH port forward in Step 7 is sufficient to use AIGoat. A host-level client is only needed for native apps or for members not using WSL. It does not make browser login work on the `100.x.y.z` address (see Step 7).

- **Windows:** `winget install --id Tailscale.Tailscale` in PowerShell, or the installer from tailscale.com/download/windows; sign in from the system tray icon.
- **macOS:** install from the Mac App Store or tailscale.com/download/mac; sign in from the menu bar icon.
- **Linux (not WSL):**

```bash
curl -fsSL https://tailscale.com/install.sh | sh   # install Tailscale
sudo tailscale up                                   # prints a login URL; open it and approve
```

Run `tailscale status` to confirm the VM appears. WSL and the Windows host appear as two separate devices, which is expected.

**Test SSH over Tailscale** before removing the public rule:

```bash
ssh azureuser@100.x.y.z
```

**Keep Tailscale SSH disabled.** This runbook uses standard key-based SSH. If `tailscale set --ssh` was enabled, Tailscale intercepts SSH and key authentication stops working. Disable it:

```bash
az vm run-command invoke -g $RG -n $VM --command-id RunShellScript --scripts "tailscale set --ssh=false"
```

**Troubleshooting `Permission denied (publickey)`.** The network path works but the VM rejected the key. Common causes: the client is offering a different key than the one installed (`az vm create --generate-ssh-keys` installs `~/.ssh/id_rsa` by default, not an ed25519 key), or the key is stored outside `~/.ssh`, where SSH does not look by default.

Try the key Azure generated:

```bash
ls ~/.ssh
ssh -i ~/.ssh/id_rsa azureuser@100.x.y.z
```

Otherwise, install your ed25519 public key via Run Command:

```bash
PUB=$(cat ~/.ssh/id_ed25519.pub)
az vm run-command invoke -g $RG -n $VM --command-id RunShellScript --scripts "echo '$PUB' >> /home/azureuser/.ssh/authorized_keys"
```

If the key lives outside `~/.ssh`, pass it explicitly with `-i <path-to-private-key>` or move it into `~/.ssh` with mode `600`.

If SSH reports that key permissions are too open, the file is probably on a Windows-mounted drive (under `/mnt/c`). Copy it into the WSL filesystem:

```bash
mkdir -p ~/.ssh && cp <path>/id_ed25519 <path>/id_ed25519.pub ~/.ssh/ && chmod 600 ~/.ssh/id_ed25519
```

To see which keys SSH offers and what the server accepts:

```bash
ssh -v azureuser@100.x.y.z 2>&1 | grep -E "Offering|Authentications|identity file"
```

**Remove the temporary public SSH rule** (from your workstation):

```bash
az network nsg rule delete -g $RG --nsg-name nsg-aigoat -n AllowInboundSSH
```

Verify: `ssh azureuser@<publicIpAddress>` should now time out, while the Tailscale address still connects.

**Optional host firewall (UFW).** Run on the VM only after the Tailscale SSH test passes. It adds a second layer behind the NSG, dropping any inbound traffic that does not arrive over Tailscale. Keep this order to avoid locking yourself out:

```bash
sudo ufw default deny incoming    # block all inbound traffic by default
sudo ufw default allow outgoing   # allow outbound (apt, git, model downloads)
sudo ufw allow in on tailscale0   # allow traffic arriving over the Tailscale interface
sudo ufw enable                   # enable the firewall (answer y to the SSH warning)
```

`allow in on tailscale0` permits inbound connections only on the Tailscale interface, so SSH (22), the frontend (3000) and the API (8000) are reachable only from the tailnet. Enabling UFW before adding that rule would drop the current SSH session.

Verify:

```bash
sudo ufw status verbose           # expect: deny (incoming), allow (outgoing), and a rule for tailscale0
```

Recovery if locked out:

```bash
az vm run-command invoke -g $RG -n $VM --command-id RunShellScript --scripts "ufw disable"
```

## Step 6: Install Ollama and deploy AIGoat

AIGoat's start script requires **Python 3.11** and exits with `[FAIL] Python 3.11 is required (CI pin / pyproject target-version)` otherwise. Ubuntu 24.04 ships Python 3.12, so install 3.11 alongside it and leave the project's `target-version` unchanged. The distribution's Node 18 package is sufficient. On the VM:

```bash
sudo apt -y install git tmux curl software-properties-common nodejs npm
sudo add-apt-repository -y ppa:deadsnakes/ppa   # additional Python versions for Ubuntu
sudo apt update
sudo apt -y install python3.11 python3.11-venv python3.11-dev
python3.11 --version                            # expect 3.11.x
node -v                                         # expect 18 or newer
```

**Install Ollama and pull the model:**

```bash
curl -fsSL https://ollama.com/install.sh | sh
ollama pull mistral
ollama run mistral "Say hello in five words"
ollama ps
```

`ollama ps` reports `100% CPU` on this VM, as expected. The first reply after an idle period is slowest because the model must load. Replies typically take 10-30 seconds, and concurrent requests queue.

**Clone and start AIGoat inside tmux** so it survives SSH disconnects:

```bash
git clone https://github.com/AISecurityConsortium/AIGoat.git
cd AIGoat
chmod +x scripts/*.sh
tmux new -s aigoat
python3.11 -m venv ~/aigoat-venv     # Python 3.11 environment
source ~/aigoat-venv/bin/activate    # makes python/python3 resolve to 3.11 in this shell
python --version                     # expect 3.11.x
./scripts/start.sh
```

Activate the environment inside tmux, and again in any new tmux window. If the script still reports the wrong version, inspect how it selects Python with `grep -n -i python scripts/start.sh`.

The first run installs Python and npm dependencies and can take several minutes. Wait for "AI Goat is running!". Detach with Ctrl+b then d; reattach with `tmux attach -t aigoat`.

The start script checks Ollama, pulls Mistral if missing, initializes the database and starts both servers. Behavior may differ between releases; if it fails, review the log output and the project's troubleshooting documentation.

**Optional agent model.** The script may warn that the tool-calling model `qwen3.5:9b` is not installed. The agent, MCP host and kill-chain labs need it for tool calls; all other labs run on Mistral. Install it with `ollama pull qwen3.5:9b` (a multi-gigabyte download that needs more RAM and is slow on CPU), or start with `AIGOAT_PULL_AGENT_MODEL=1 ./scripts/start.sh`. Defer it until those labs are needed.

## Step 7: Access the app from team workstations and smoke-test

Each member connects to Tailscale, forwards both app ports over SSH, and opens the app at `http://localhost:3000`. This is the supported access path: the frontend (3000) calls the backend (8000) from the browser, and the backend's CORS policy accepts only the `localhost` origin.

```bash
ssh -L 3000:localhost:3000 -L 8000:localhost:8000 azureuser@100.x.y.z
```

Add `-i <path-to-private-key>` if the key is not in `~/.ssh`. Keep the session open and browse to http://localhost:3000 (API docs at http://localhost:8000/docs).

**Do not browse to the Tailscale address.** `http://100.x.y.z:3000` loads the pages, but login fails: the browser's CORS preflight (`OPTIONS /api/auth/login/`) originates from that address and the backend returns `400 Bad Request`, visible in `logs/backend.log`. For direct access, add that origin to the backend's CORS settings; locate them with `grep -rn -i -E "cors|allow_origins" ~/AIGoat/app ~/AIGoat/config`.

**WSL users:** the Windows browser cannot use WSL's Tailscale connection. Use the port forward above and browse to `http://localhost:3000`.

**Smoke test** (run once with the whole team):

- Log in with one of AIGoat's default seeded accounts (`alice`, `bob`, `charlie`, `frank` with `password123`; `admin` with `admin123`). Assign one account per member so chats and CTF progress stay separate. These are public lab defaults; never reuse them elsewhere.
- Send a chat message and time the reply. Expect 10-30 seconds on CPU. Over a minute indicates resource pressure; check `htop` and `free -h`.
- Open an Attack Lab and a CTF challenge, and confirm the defense-level toggle in the navigation bar works.
- **Test for shared state.** With two members logged in, have one add a Knowledge Base entry and sync it to the vector database; check whether the other member's chatbot is affected, and whether the defense level is global. Have two members send a message simultaneously to measure queuing. If state is shared, coordinate which lab each member works on.

**If login fails with "Invalid credentials" for every user:** first confirm the app was opened at `http://localhost:3000` through the port forward. Via the Tailscale address, the preflight fails with `400` and the UI shows a generic error (`tail -n 30 ~/AIGoat/logs/backend.log`). After switching, use a private window or hard refresh (Ctrl+Shift+R). Only if the backend log shows the login `POST` itself failing (for example `401`) is the database at fault.

By default the start script builds and runs the backend from `~/AIGoat/venv`. To reseed with that environment:

```bash
cd ~/AIGoat
./scripts/stop.sh
source ~/AIGoat/venv/bin/activate
python -c "import sqlalchemy; print(sqlalchemy.__version__)"   # must print a version, not an error
python -m scripts.seed                                          # expect: Seed completed successfully.
./scripts/start.sh
```

If the backend uses a different interpreter, identify it from the running process:

```bash
PID=$(ss -tlnp | grep ':8000' | grep -o 'pid=[0-9]*' | cut -d= -f2)
tr '\0' ' ' < /proc/$PID/cmdline; echo    # for example /home/azureuser/AIGoat/venv/bin/python3 ...
```

Then run `<PYTHON> -m scripts.seed` from `~/AIGoat` with that path. If nothing is listening on 8000, install dependencies into your own venv and seed with it:

```bash
cd ~/AIGoat
source ~/aigoat-venv/bin/activate
pip install -r requirements.txt
python -m scripts.seed
```

**Seed script cautions**

- A full run resets the passwords of the five default accounts and recreates the shop data.
- A full run deletes all CTF challenge attempts. Once members have progress, use `python -m scripts.seed --sync-challenges`, which updates challenge text and keeps attempts.
- Each full run adds 6-8 random orders per demo user. To refresh only support tickets, use `python -m scripts.seed --sync-support`.
- Run it from `~/AIGoat` so it writes to the database the backend reads.

If the start script reports `Database already has required data` after a reseed and login still fails, the cause is the browser origin, not the database. Check the request URL in DevTools.

## Step 8: Operations, cost control and teardown

The VM bills for compute, disk and public IP while allocated. Always deallocate; an OS-level shutdown leaves the VM in a "stopped" state that still incurs compute charges.

**Start and stop** (from any workstation with the Azure CLI):

```bash
az vm start -g $RG -n $VM
az vm deallocate -g $RG -n $VM
az vm list -g $RG -d -o table
```

The power state should read `VM deallocated` when finished. The Tailscale address persists across restarts.

**After each start**, SSH in, run `tmux new -s aigoat`, then `cd ~/AIGoat && ./scripts/start.sh`. Ollama starts automatically as a service, and models persist on disk.

**Take a baseline snapshot** after the smoke test passes, so you can roll back after destructive experiments:

```bash
OSDISK=$(az vm show -g $RG -n $VM --query storageProfile.osDisk.managedDisk.id -o tsv)
az snapshot create -g $RG -n snap-aigoat-baseline --source $OSDISK
```

**Team rules**

- Announce before running `./scripts/stop.sh --clean && ./scripts/start.sh`; it resets the database for everyone.
- Attack only the AIGoat app on this VM. No scanning or fuzzing of other targets and no network flooding. The Unbounded Consumption lab (token flooding the model) is in scope because it stays on the VM.
- Never expose ports 3000 or 8000 to the internet, and never add a public inbound rule.
- The last member to finish confirms the VM is deallocated.

**Teardown** at the end of the engagement deletes the VM, disk, snapshot, network and IP together:

```bash
az group delete -n $RG --yes --no-wait
```

Then remove the `aigoat-azure` machine from the Tailscale admin console.

## Step 9: Stopping, starting and resuming the app

There are two layers: the application processes on the VM, and the VM itself (which Azure bills for). Stopping the app does not stop billing; deallocating the VM does.

**Stop the app** (VM stays running):

```bash
cd ~/AIGoat
./scripts/stop.sh        # stops frontend and backend; Ollama keeps running as a system service
```

**Start the app inside tmux:**

```bash
tmux new -s aigoat       # or `tmux attach -t aigoat` if the session exists
cd ~/AIGoat
./scripts/start.sh       # wait for "AI Goat is running!"
```

The start script uses its own environment at `~/AIGoat/venv`, so no manual activation is needed. If it reports the wrong Python version, install Python 3.11 as in Step 6. Detach with Ctrl+b, then d.

**Verify it is running:**

```bash
ss -tlnp | grep -E '3000|8000'     # both ports should be listening
tail -n 20 ~/AIGoat/logs/backend.log
```

**Resuming:**

| Situation | Action |
| --- | --- |
| SSH session dropped, VM still running | SSH back in and run `tmux attach -t aigoat`; the app kept running |
| VM was deallocated (auto-shutdown or manual) | Run `az vm start -g $RG -n $VM` and wait about a minute. Tailscale reconnects automatically. SSH in and start the app again with the tmux commands above; tmux sessions do not survive a shutdown |
| Browser cannot connect | The local SSH tunnel is closed. Re-run the `ssh -L` command from Step 7 and keep that terminal open |
| A clean database is needed | Notify the team, then run `./scripts/stop.sh --clean && ./scripts/start.sh`. This resets everyone's data |

**tmux reference:** `tmux ls` lists sessions, `tmux attach -t aigoat` reattaches, `tmux kill-session -t aigoat` removes a session. Detach without stopping the app with Ctrl+b, then d.

**End of day:** optionally stop the app, then deallocate the VM:

```bash
az vm deallocate -g $RG -n $VM
az vm list -g $RG -d -o table    # PowerState should read: VM deallocated
```

## Step 10: Quick start (daily routine)

Once setup is complete, each session follows the same steps. Run them manually, or use the script below to do them in one command.

### Manual steps

1. **Start the VM** if it was deallocated (from your workstation):

   ```bash
   az vm start -g $RG -n $VM
   ```

2. **Confirm the VM is on the tailnet:**

   ```bash
   tailscale ping 100.x.y.z
   ```

3. **Start the app in tmux on the VM.** This creates the session only if it does not exist, and starts the app only if ports 3000 and 8000 are not already listening:

   ```bash
   ssh azureuser@100.x.y.z
   ss -tln | grep -E ':(3000|8000) '   # two lines means the app is already running; skip to step 4
   tmux new -A -s aigoat               # attach to the session, or create it
   cd ~/AIGoat && ./scripts/start.sh   # wait for "AI Goat is running!", then Ctrl+b, d
   exit
   ```

4. **Open the tunnel** from your workstation and keep the terminal open:

   ```bash
   ssh -N -L 3000:localhost:3000 -L 8000:localhost:8000 azureuser@100.x.y.z
   ```

5. **Browse to** http://localhost:3000. Ctrl+C in the tunnel terminal closes the tunnel; the app keeps running on the VM.

### Script

Save this on your workstation (WSL, Linux or macOS) as `~/bin/aigoat-start.sh`, outside the repository, and set `HOST` to the VM's Tailscale IP. Keep the real IP out of version control.

```bash
#!/usr/bin/env bash
# Start AIGoat on the team VM over Tailscale and open the SSH tunnel.
# Usage: aigoat-start.sh [--start-vm] [--no-tunnel]
set -euo pipefail

HOST="100.x.y.z"          # VM Tailscale IP (tailscale ip -4 on the VM)
USER_NAME="azureuser"
SSH_KEY=""                # optional, for example ~/.ssh/id_ed25519
RG="rg-aigoat"
VM="vm-aigoat"
TIMEOUT=600               # seconds to wait for the app; the first run is slow

START_VM=0; TUNNEL=1
for arg in "$@"; do
  case "$arg" in
    --start-vm)  START_VM=1 ;;
    --no-tunnel) TUNNEL=0 ;;
    *) echo "Usage: $0 [--start-vm] [--no-tunnel]" >&2; exit 1 ;;
  esac
done

SSH_OPTS=(-o ConnectTimeout=10 -o ServerAliveInterval=30)
[[ -n "$SSH_KEY" ]] && SSH_OPTS+=(-i "$SSH_KEY")
TARGET="$USER_NAME@$HOST"

# 1. Start the VM if requested (auto-shutdown deallocates it nightly).
if (( START_VM )); then
  echo "Starting VM $VM..."
  az vm start -g "$RG" -n "$VM" --output none
fi

# 2. Wait for SSH over Tailscale (up to 3 minutes).
echo "Connecting to $TARGET..."
for i in $(seq 1 18); do
  ssh "${SSH_OPTS[@]}" "$TARGET" true 2>/dev/null && break
  (( i == 18 )) && { echo "Cannot reach $TARGET. Check tailscale status and that the VM is running." >&2; exit 1; }
  sleep 10
done

# 3. Start the app in tmux unless it is already running, then wait for both ports.
ssh "${SSH_OPTS[@]}" "$TARGET" bash -s -- "$TIMEOUT" <<'REMOTE'
set -euo pipefail
timeout="$1"
ports_up() { ss -tln | grep -q ':3000 ' && ss -tln | grep -q ':8000 '; }
if ports_up; then echo "AIGoat is already running."; exit 0; fi
tmux has-session -t aigoat 2>/dev/null || tmux new-session -d -s aigoat -c "$HOME/AIGoat"
tmux send-keys -t aigoat "cd ~/AIGoat && ./scripts/start.sh" C-m
echo "Starting AIGoat (the first run can take several minutes)..."
for (( t = 0; t < timeout; t += 5 )); do
  ports_up && { echo "AIGoat is running."; exit 0; }
  sleep 5
done
echo "Timed out. Last output from the tmux session:" >&2
tmux capture-pane -p -t aigoat | tail -n 20 >&2
exit 1
REMOTE

# 4. Forward the app ports; the backend only accepts the localhost origin.
if (( TUNNEL )); then
  echo "Tunnel open: browse to http://localhost:3000 (Ctrl+C to close; the app keeps running)."
  exec ssh "${SSH_OPTS[@]}" -N -o ExitOnForwardFailure=yes \
    -L 3000:localhost:3000 -L 8000:localhost:8000 "$TARGET"
fi
```

Make it executable and run it:

```bash
chmod +x ~/bin/aigoat-start.sh
~/bin/aigoat-start.sh --start-vm    # after auto-shutdown; omit the flag if the VM is already running
```

Notes:

- `--start-vm` needs the Azure CLI signed in (`az login`). `--no-tunnel` starts the app without opening the tunnel.
- If your key has a passphrase, load it with `ssh-add` first so the connection retries do not prompt repeatedly.
- If the script times out, attach to the session with `ssh azureuser@100.x.y.z` and `tmux attach -t aigoat` to see the full output.
- `ExitOnForwardFailure` stops the tunnel if local port 3000 or 8000 is already in use. Close the other process or the previous tunnel first.

## Troubleshooting

| Symptom | Likely cause | Fix |
| --- | --- | --- |
| `QuotaExceeded` or `OperationNotAllowed` creating the VM | Not enough free vCPUs in the region | Request more DASv5 and regional vCPUs, or use `Standard_D4as_v5` (Step 1) |
| `SkuNotAvailable` | Size restricted or out of capacity in that region | Use `Standard_D8s_v5`, or recreate the resource group and network in another region |
| `[FAIL] Python 3.11 is required` from start.sh | Ubuntu 24.04 ships Python 3.12 | Install 3.11 from the deadsnakes PPA and activate a 3.11 venv before running the script (Step 6); do not change `target-version` |
| Chat takes 10-30 seconds | Expected on CPU | Use `tinyllama` for easier labs, add vCPUs, or add a GPU |
| Chat takes over a minute or times out | Concurrent prompts or insufficient RAM | One member per lab at a time; check `free -h` and `htop` |
| `lscpu` shows no `avx2` | Unsuitable VM size | Resize to a Dasv5 or Dsv5 size |
| start.sh reports Ollama not reachable | Ollama service not running | `sudo systemctl status ollama`, then `sudo systemctl start ollama` |
| SSH to `100.x.y.z` fails or times out | Client not on the tailnet, VM deallocated, or node key expired | Install Tailscale inside WSL (Step 5); `az vm start`; check `tailscale status` and key expiry in the admin console |
| `Permission denied (publickey)` | Public key missing from `authorized_keys`, wrong key offered, or Tailscale SSH enabled | Pass the correct key with `-i` or move it into `~/.ssh`, add it with Azure Run Command, and disable Tailscale SSH (Step 5) |
| Pages load but login or chat fails | App opened via `100.x.y.z`; backend rejects that origin (CORS preflight returns 400 in `logs/backend.log`) | Forward ports 3000 and 8000 over SSH and open http://localhost:3000 (Step 7) |
| Port already in use | Previous run still alive | `./scripts/stop.sh`, then start again |
| Still being charged after "stopping" | VM stopped but not deallocated | `az vm deallocate`; confirm with `az vm list -d` |
