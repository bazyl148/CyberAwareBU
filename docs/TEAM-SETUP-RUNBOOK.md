# AIGoat on Azure: Team Setup Runbook

Deploy AIGoat on a private, CPU-only Azure VM that only your team can reach over Tailscale, then run it day to day at minimal cost.

**Audience:** team members setting up or operating the lab · **Time:** about 1 hour for initial setup · **Applies to:** Ubuntu Server 24.04 LTS, Azure CLI, Tailscale, AIGoat

---

## Contents

- [Before you begin](#before-you-begin)
  - [Architecture at a glance](#architecture-at-a-glance)
  - [Prerequisites](#prerequisites)
  - [Conventions](#conventions)
  - [Rules of engagement](#rules-of-engagement)
- [Part 1: Initial setup](#part-1-initial-setup)
  1. [Install the Azure CLI](#step-1-install-the-azure-cli)
  2. [Check credits, VM size and quota](#step-2-check-credits-vm-size-and-quota)
  3. [Create the network](#step-3-create-the-network)
  4. [Create the VM](#step-4-create-the-vm)
  5. [Update the VM and verify the CPU](#step-5-update-the-vm-and-verify-the-cpu)
  6. [Add Tailscale and close public access](#step-6-add-tailscale-and-close-public-access)
  7. [Install Ollama and AIGoat](#step-7-install-ollama-and-aigoat)
  8. [Connect and smoke-test](#step-8-connect-and-smoke-test)
- [Part 2: Daily operations](#part-2-daily-operations)
  - [Quick start](#quick-start)
  - [Stop the app and the VM](#stop-the-app-and-the-vm)
  - [Resume after a break](#resume-after-a-break)
  - [Snapshots](#snapshots)
  - [Cost control](#cost-control)
  - [Teardown](#teardown)
- [Reference](#reference)
  - [Team rules](#team-rules)
  - [Command cheat sheet](#command-cheat-sheet)
  - [Troubleshooting](#troubleshooting)
  - [Optional: GPU acceleration](#optional-gpu-acceleration)

### Jump to a task

| I want to... | Go to |
| --- | --- |
| Start the app for today's session | [Quick start](#quick-start) |
| Use the one-command start script | [Quick start script](#quick-start-script) |
| Give a new team member access | [Grant team members SSH access](#grant-team-members-ssh-access) |
| Fix `Permission denied (publickey)` | [SSH permission denied](#ssh-permission-denied) |
| Fix a login that fails for every user | [Login fails for every user](#login-fails-for-every-user) |
| Reset or reseed the database | [Reseeding the database](#reseeding-the-database) |
| Stop paying for the VM | [Stop the app and the VM](#stop-the-app-and-the-vm) |
| Delete everything | [Teardown](#teardown) |

---

## Before you begin

### Architecture at a glance

```
Workstation (WSL / Linux / macOS)                 Azure VM (no inbound ports open)
┌────────────────────────────┐   Tailscale    ┌──────────────────────────────────┐
│ browser → localhost:3000 ──┼── SSH tunnel ──┼─▶ :3000 React frontend           │
│           localhost:8000 ──┼────────────────┼─▶ :8000 FastAPI backend          │
└────────────────────────────┘                │        └─▶ Ollama (Mistral, CPU) │
                                              └──────────────────────────────────┘
```

| Item | Choice |
| --- | --- |
| Region | Any region where the VM size is available to your subscription |
| VM size | `Standard_D8as_v5`: 8 vCPU (AMD), 32 GB RAM, no GPU. Use `Standard_D4as_v5` (4 vCPU, 16 GB) if quota is limited to 4 vCPUs |
| OS and disk | Ubuntu Server 24.04 LTS, 64 GB StandardSSD |
| Access | Tailscale only; no inbound rules left open on the Azure NSG |
| Cost guard | Auto-shutdown, budget alert, resource group deletion at teardown |
| App | AIGoat via `./scripts/start.sh` (Ollama + Mistral on CPU) |

> [!NOTE]
> The CPU-only VM works on subscriptions without GPU quota. Chat replies take roughly 10-30 seconds and concurrent requests queue, but every lab and challenge works. See [Optional: GPU acceleration](#optional-gpu-acceleration) for faster options.

### Prerequisites

- An Azure subscription with credits and Contributor (or Owner) rights
- Azure CLI on your workstation or WSL ([Step 1](#step-1-install-the-azure-cli)), signed in with `az login`
- A Tailscale account for each team member (check the current free-plan user limit)
- About one hour, plus any wait for quota approval

### Conventions

Commands use these shell variables. Set them once per terminal session on your workstation:

```bash
RG=rg-aigoat
LOC=<region>        # for example eastus, westeurope, canadacentral
VM=vm-aigoat
```

| Placeholder | Meaning |
| --- | --- |
| `100.x.y.z` | The VM's Tailscale IPv4 address (`tailscale ip -4` on the VM) |
| `<publicIpAddress>` | The VM's Azure public IP, used only during initial setup |
| **On the VM** / **On your workstation** | Where to run a command block |

### Rules of engagement

> [!IMPORTANT]
> Attack only the AIGoat instance running on your own VM. Do not point scanners or fuzzers at any other target, and do not perform denial-of-service testing. This follows Microsoft's penetration testing rules of engagement; review them before starting. See also [Team rules](#team-rules).

[↑ Back to top](#contents)

---

## Part 1: Initial setup

Run these steps once, in order. Each step lists where its commands run.

### Step 1: Install the Azure CLI

**On your workstation** (Ubuntu, including WSL 2):

```bash
curl -sL https://aka.ms/InstallAzureCLIDeb | sudo bash   # Microsoft's official installer for Debian and Ubuntu
az --version                                             # confirm the install
az login                                                 # opens a browser to sign in
```

> [!TIP]
> The installer runs as root. To review it first: `curl -sL https://aka.ms/InstallAzureCLIDeb -o install.sh`, inspect it with `less install.sh`, then run `sudo bash install.sh`. On WSL, if `az login` does not open a browser, use `az login --use-device-code`.

### Step 2: Check credits, VM size and quota

You need 8 free vCPUs in one region (4 for the smaller size). Free-trial subscriptions are often capped at 4 vCPUs per region.

1. In the portal, open **Subscriptions** and note the offer type. Under **Cost Management + Billing**, check the credit balance and expiry date.
2. Confirm the VM size is offered in your region:

   ```bash
   az account set --subscription "<name or id>"
   az vm list-skus --location $LOC --size Standard_D8as_v5 --output table
   ```

   If the output shows a restriction such as `NotAvailableForSubscription`, choose another region and update `LOC`.

3. Check quota for the AMD Dasv5 family and the regional total:

   ```bash
   az vm list-usage --location $LOC --output table | grep -i -E "DASv5|Total Regional"
   ```

   Free vCPUs equal the limit minus current usage. You need 8 free on both `Standard DASv5 Family vCPUs` and `Total Regional vCPUs` (4 for `Standard_D4as_v5`).

4. If the limit is too low, request an increase: **Subscriptions → Usage + quotas**, filter on "DASv5", and request a new limit of 8. CPU quota requests are usually approved within minutes.

> [!NOTE]
> On a free trial capped at 4 vCPUs, either use `Standard_D4as_v5` or upgrade to pay-as-you-go (remaining credits normally carry over). If Dasv5 sizes are restricted in your region, use `Standard_D8s_v5` (Intel) and change the size in [Step 4](#step-4-create-the-vm).

### Step 3: Create the network

Keep every resource in one resource group so a single delete removes everything.

**On your workstation** (not Azure Cloud Shell, because the SSH rule uses your workstation's public IP):

```bash
az group create -n $RG -l $LOC

az network vnet create -g $RG -n vnet-aigoat \
  --address-prefixes 10.20.0.0/16 \
  --subnet-name snet-vm --subnet-prefixes 10.20.1.0/24

az network nsg create -g $RG -n nsg-aigoat
```

Add one **temporary** SSH rule restricted to your public IP. It is used only for initial setup and removed in [Step 6](#remove-public-ssh-access):

```bash
MYIP=$(curl -s https://ifconfig.me)
az network nsg rule create -g $RG --nsg-name nsg-aigoat \
  -n AllowInboundSSH --priority 100 --access Allow \
  --direction Inbound --protocol Tcp \
  --destination-port-ranges 22 --source-address-prefixes $MYIP/32
```

Azure's default NSG rules deny all other inbound internet traffic. Ports 3000 and 8000 are never opened.

Finally, set a budget alert as described in [Cost control](#cost-control).

### Step 4: Create the VM

**On your workstation:**

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

Copy `publicIpAddress` from the output and connect:

```bash
ssh azureuser@<publicIpAddress>
```

Design notes:

- `--security-type Standard` avoids Secure Boot issues if a GPU driver is added later.
- The public IP is kept only for outbound internet access (package and model downloads). Once the SSH rule is removed in Step 6, no inbound connection is possible from outside.
- The auto-shutdown time is in **UTC**; convert it to a time that suits your team's working hours. Auto-shutdown deallocates the VM, which stops compute billing.

> [!WARNING]
> `--generate-ssh-keys` stores the admin key pair under `~/.ssh` on the machine that ran the command. Back it up; losing it means losing admin access.

### Step 5: Update the VM and verify the CPU

**On the VM:**

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

**Expected:** `avx2`, 8 CPUs and about 31 GB of memory (4 CPUs and about 15 GB on the smaller size). If `avx2` is missing, inference will be much slower; choose a different size.

### Step 6: Add Tailscale and close public access

Tailscale gives the VM a private address reachable only from devices on your tailnet, so no inbound port needs to be open on Azure.

#### Join the VM to the tailnet

**On the VM:**

```bash
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up --hostname=aigoat-azure
tailscale ip -4
```

Open the printed login URL and approve the device. Record the `100.x.y.z` address.

In the **Tailscale admin console**:

- Disable key expiry for this machine so it does not drop off the tailnet.
- Invite team members to the tailnet, or share the machine with their Tailscale accounts.

#### Grant team members SSH access

Each member sends their public key, a single line beginning with `ssh-ed25519`:

```bash
cat ~/.ssh/id_ed25519.pub     # generate one first with ssh-keygen -t ed25519 if needed
```

**On your workstation**, append each key with Azure Run Command, which works even when SSH does not:

```bash
az vm run-command invoke -g $RG -n $VM --command-id RunShellScript \
  --scripts "echo 'ssh-ed25519 AAAA...paste-key-here member-name' >> /home/azureuser/.ssh/authorized_keys"
```

> [!WARNING]
> Use `>>` to append. A single `>` overwrites `authorized_keys` and locks everyone out. Only the `.pub` file is ever shared; private keys never leave their owner's machine.

A single shared Linux account is acceptable for a small lab team; for larger teams, create one account per user.

#### Join a WSL workstation to the tailnet

If your SSH key and Azure CLI live in WSL, WSL needs its own Tailscale connection, even when Tailscale for Windows is installed.

1. Confirm systemd is running:

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

2. Install Tailscale and sign in to the same tailnet as the VM:

   ```bash
   curl -fsSL https://tailscale.com/install.sh | sh
   sudo tailscale up --hostname=workstation-wsl
   ```

3. Verify connectivity:

   ```bash
   tailscale status
   tailscale ping 100.x.y.z
   ```

> [!TIP]
> Use the `100.x.y.z` address for SSH rather than the MagicDNS name; WSL often does not resolve Tailscale names.

#### Install Tailscale on other operating systems (optional)

The SSH tunnel in [Step 8](#step-8-connect-and-smoke-test) is sufficient to use AIGoat. A host-level client is only needed for native apps or for members not using WSL. It does **not** make browser login work on the `100.x.y.z` address.

| OS | Install |
| --- | --- |
| Windows | `winget install --id Tailscale.Tailscale`, or the installer from tailscale.com/download/windows; sign in from the system tray |
| macOS | Mac App Store or tailscale.com/download/mac; sign in from the menu bar |
| Linux (not WSL) | `curl -fsSL https://tailscale.com/install.sh \| sh`, then `sudo tailscale up` |

Run `tailscale status` to confirm the VM appears. WSL and the Windows host appear as two separate devices, which is expected.

#### Test SSH over Tailscale

```bash
ssh azureuser@100.x.y.z
```

If this fails with `Permission denied (publickey)`, see [SSH permission denied](#ssh-permission-denied).

> [!IMPORTANT]
> **The team VM runs Tailscale SSH** (`tailscale set --ssh`). Tailscale answers on port 22 and logs you in by your tailnet identity, so no SSH key or `-i` flag is needed, and `authorized_keys` is not consulted. Access is granted by adding the person to the tailnet (and its SSH policy), not by adding their key.
>
> To go back to standard key-based SSH instead, turn it off:
> ```bash
> az vm run-command invoke -g $RG -n $VM --command-id RunShellScript --scripts "tailscale set --ssh=false"
> ```
> With it off, follow [Grant team members SSH access](#grant-team-members-ssh-access) for keys.

#### Remove public SSH access

**On your workstation**, only after the Tailscale SSH test passes:

```bash
az network nsg rule delete -g $RG --nsg-name nsg-aigoat -n AllowInboundSSH
```

**Verify:** `ssh azureuser@<publicIpAddress>` now times out, while the Tailscale address still connects.

#### Add a host firewall (optional)

UFW adds a second layer behind the NSG, dropping any inbound traffic that does not arrive over Tailscale. **On the VM**, keep this order to avoid locking yourself out:

```bash
sudo ufw default deny incoming    # block all inbound traffic by default
sudo ufw default allow outgoing   # allow outbound (apt, git, model downloads)
sudo ufw allow in on tailscale0   # allow traffic arriving over the Tailscale interface
sudo ufw enable                   # enable the firewall (answer y to the SSH warning)
sudo ufw status verbose           # expect: deny (incoming), allow (outgoing), and a rule for tailscale0
```

SSH (22), the frontend (3000) and the API (8000) are then reachable only from the tailnet. If you get locked out, see [Locked out by UFW](#locked-out-by-ufw).

### Step 7: Install Ollama and AIGoat

#### Install Python 3.11 and Node

AIGoat's start script requires **Python 3.11** and exits with `[FAIL] Python 3.11 is required (CI pin / pyproject target-version)` otherwise. Ubuntu 24.04 ships Python 3.12, so install 3.11 alongside it.

> [!IMPORTANT]
> Do not change the project's `target-version` to work around the Python check.

**On the VM:**

```bash
sudo apt -y install git tmux curl software-properties-common nodejs npm
sudo add-apt-repository -y ppa:deadsnakes/ppa   # additional Python versions for Ubuntu
sudo apt update
sudo apt -y install python3.11 python3.11-venv python3.11-dev
python3.11 --version                            # expect 3.11.x
node -v                                         # expect 18 or newer
```

#### Install Ollama and pull the model

```bash
curl -fsSL https://ollama.com/install.sh | sh
ollama pull mistral
ollama run mistral "Say hello in five words"
ollama ps                                       # expect 100% CPU on this VM
```

The first reply after an idle period is slowest because the model must load.

#### Clone and start AIGoat

Run the app inside tmux so it survives SSH disconnects:

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

The first run installs Python and npm dependencies and can take several minutes. Wait for **"AI Goat is running!"**, then detach with **Ctrl+b, d**. Reattach later with `tmux attach -t aigoat`.

The start script checks Ollama, pulls Mistral if missing, initializes the database and starts both servers. If it still reports the wrong Python version, inspect how it selects Python with `grep -n -i python scripts/start.sh`.

> [!NOTE]
> **Optional agent model.** The script may warn that the tool-calling model `qwen3.5:9b` is not installed. Only the agent, MCP host and kill-chain labs need it; all other labs run on Mistral. Install it later with `ollama pull qwen3.5:9b` (multi-gigabyte, needs more RAM, slow on CPU) or start with `AIGOAT_PULL_AGENT_MODEL=1 ./scripts/start.sh`.

### Step 8: Connect and smoke-test

#### Open the app through an SSH tunnel

The frontend (3000) calls the backend (8000) from the browser, and the backend's CORS policy accepts only the `localhost` origin. **On your workstation:**

```bash
ssh -L 3000:localhost:3000 -L 8000:localhost:8000 azureuser@100.x.y.z
```

Keep the session open and browse to http://localhost:3000 (API docs at http://localhost:8000/docs). Add `-i <path-to-private-key>` if your key is not in `~/.ssh`.

> [!WARNING]
> Do not browse to `http://100.x.y.z:3000`. Pages load, but login fails because the backend rejects the CORS preflight from that origin with `400 Bad Request`. WSL users must also use the tunnel, since the Windows browser cannot use WSL's Tailscale connection.

#### Run the smoke test

Run once with the whole team:

- [ ] Log in with one of AIGoat's default seeded accounts: `alice`, `bob`, `charlie`, `frank` (`password123`) or `admin` (`admin123`). Assign one account per member so chats and CTF progress stay separate.
- [ ] Send a chat message and time the reply. Expect 10-30 seconds on CPU; over a minute indicates resource pressure (check `htop` and `free -h`).
- [ ] Open an Attack Lab and a CTF challenge, and confirm the defense-level toggle in the navigation bar works.
- [ ] **Test for shared state.** With two members logged in, have one add a Knowledge Base entry and sync it to the vector database. Check whether the other member's chatbot is affected and whether the defense level is global. Send two messages simultaneously to measure queuing. If state is shared, coordinate which lab each member works on.

> [!NOTE]
> The default accounts are public lab credentials. Never reuse them elsewhere.

Once the smoke test passes, take a [baseline snapshot](#snapshots).

[↑ Back to top](#contents)

---

## Part 2: Daily operations

There are two layers: the application processes on the VM, and the VM itself, which Azure bills for. Stopping the app does not stop billing; deallocating the VM does.

### Quick start

Each session follows the same steps. Run them manually, or use the [quick start script](#quick-start-script) to do them in one command.

#### Manual steps

1. **Start the VM** if it was deallocated (on your workstation):

   ```bash
   az vm start -g $RG -n $VM
   ```

2. **Confirm the VM is on the tailnet:**

   ```bash
   tailscale ping 100.x.y.z
   ```

3. **Start the app in tmux on the VM**, unless ports 3000 and 8000 are already listening:

   ```bash
   ssh azureuser@100.x.y.z
   ss -tln | grep -E ':(3000|8000) '   # two lines means the app is already running; skip to step 4
   tmux new -A -s aigoat               # attach to the session, or create it
   cd ~/AIGoat && ./scripts/start.sh   # wait for "AI Goat is running!", then Ctrl+b, d
   exit
   ```

4. **Open the tunnel** on your workstation and keep the terminal open:

   ```bash
   ssh -N -L 3000:localhost:3000 -L 8000:localhost:8000 azureuser@100.x.y.z
   ```

5. **Browse to** http://localhost:3000. Ctrl+C in the tunnel terminal closes the tunnel; the app keeps running on the VM.

#### Quick start script

Save this on your workstation (WSL, Linux or macOS) as `~/bin/aigoat-start.sh` and set `HOST` to the VM's Tailscale IP.

> [!WARNING]
> Keep the script outside the repository so the real Tailscale IP never reaches version control.

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

Make it executable, convert it to Unix line endings, and run it:

```bash
chmod +x ~/bin/aigoat-start.sh
sed -i 's/\r$//' ~/bin/aigoat-start.sh   # strip Windows (CRLF) line endings
~/bin/aigoat-start.sh --start-vm    # after auto-shutdown; omit the flag if the VM is already running
```

> [!IMPORTANT]
> If the script fails with `env: 'bash\r': No such file or directory`, it has Windows (CRLF) line endings, usually because it was pasted or saved in a Windows editor. Run `sed -i 's/\r$//' ~/bin/aigoat-start.sh` again **after every edit**, or set your editor to save with LF endings (in VS Code, click **CRLF** in the status bar and choose **LF**). `file ~/bin/aigoat-start.sh` shows "CRLF line terminators" when the fix is needed.

| Option | Effect |
| --- | --- |
| `--start-vm` | Runs `az vm start` first; requires `az login` |
| `--no-tunnel` | Starts the app without opening the tunnel |

Notes:

- If your key has a passphrase, load it with `ssh-add` first so the connection retries do not prompt repeatedly.
- If the script times out, SSH in and run `tmux attach -t aigoat` to see the full output.
- `ExitOnForwardFailure` stops the tunnel if local port 3000 or 8000 is already in use. Close the other process or the previous tunnel first.

### Stop the app and the VM

**Stop the app** (VM stays running; Ollama keeps running as a system service):

```bash
cd ~/AIGoat && ./scripts/stop.sh
```

**Deallocate the VM** at the end of the day (on your workstation):

```bash
az vm deallocate -g $RG -n $VM
az vm list -g $RG -d -o table    # PowerState should read: VM deallocated
```

> [!WARNING]
> Always deallocate. An OS-level shutdown leaves the VM "stopped" but still allocated, and compute charges continue.

### Resume after a break

| Situation | Action |
| --- | --- |
| SSH session dropped, VM still running | SSH back in and run `tmux attach -t aigoat`; the app kept running |
| VM was deallocated (auto-shutdown or manual) | Follow the [Quick start](#quick-start). Tailscale reconnects automatically and its address does not change, but tmux sessions do not survive a shutdown |
| Browser cannot connect | The local SSH tunnel is closed. Re-run the tunnel command and keep that terminal open |
| A clean database is needed | Notify the team, then run `./scripts/stop.sh --clean && ./scripts/start.sh`. This resets everyone's data |

Verify the app is running:

```bash
ss -tlnp | grep -E '3000|8000'     # both ports should be listening
tail -n 20 ~/AIGoat/logs/backend.log
```

### Snapshots

Take a baseline snapshot after the smoke test passes, so you can roll back after destructive experiments. Snapshots are cheap but not free.

```bash
OSDISK=$(az vm show -g $RG -n $VM --query storageProfile.osDisk.managedDisk.id -o tsv)
az snapshot create -g $RG -n snap-aigoat-baseline --source $OSDISK
```

### Cost control

The VM bills for compute, disk and public IP while allocated.

- **Budget alert:** in the portal, **Cost Management → Budgets → Add**. Scope it to the resource group and add alerts at 50%, 80% and 100%.
- **Credit balance:** budgets track spend, not credits, so review the balance under **Cost Management + Billing** weekly.
- **Estimate:** compare the monthly price of the VM size in the Azure pricing calculator with your remaining credits before leaving it running for extended periods.
- **Auto-shutdown** deallocates the VM nightly at the time set in [Step 4](#step-4-create-the-vm).

### Teardown

At the end of the engagement, delete the VM, disk, snapshots, network and IP together:

```bash
az group delete -n $RG --yes --no-wait
```

Then remove the `aigoat-azure` machine from the Tailscale admin console.

> [!CAUTION]
> Deleting the resource group is irreversible.

[↑ Back to top](#contents)

---

## Reference

### Team rules

- Announce before running `./scripts/stop.sh --clean && ./scripts/start.sh`; it resets the database for everyone.
- Attack only the AIGoat app on this VM. No scanning or fuzzing of other targets and no network flooding. The Unbounded Consumption lab (token flooding the model) is in scope because it stays on the VM.
- Never expose ports 3000 or 8000 to the internet, and never add a public inbound rule.
- The last member to finish confirms the VM is deallocated.

### Command cheat sheet

| Task | Where | Command |
| --- | --- | --- |
| Start the VM | Workstation | `az vm start -g $RG -n $VM` |
| Deallocate the VM | Workstation | `az vm deallocate -g $RG -n $VM` |
| VM power state | Workstation | `az vm list -g $RG -d -o table` |
| Open the tunnel | Workstation | `ssh -N -L 3000:localhost:3000 -L 8000:localhost:8000 azureuser@100.x.y.z` |
| Attach to the app session | VM | `tmux attach -t aigoat` (`tmux ls` lists sessions) |
| Detach, leaving the app running | VM | Ctrl+b, then d |
| Start the app | VM | `cd ~/AIGoat && ./scripts/start.sh` |
| Stop the app | VM | `cd ~/AIGoat && ./scripts/stop.sh` |
| Reset the database | VM | `./scripts/stop.sh --clean && ./scripts/start.sh` |
| Backend log | VM | `tail -n 30 ~/AIGoat/logs/backend.log` |
| Ollama status | VM | `sudo systemctl status ollama`, `ollama ps` |

### Troubleshooting

| Symptom | Likely cause | Fix |
| --- | --- | --- |
| `QuotaExceeded` or `OperationNotAllowed` creating the VM | Not enough free vCPUs in the region | Request more DASv5 and regional vCPUs, or use `Standard_D4as_v5` ([Step 2](#step-2-check-credits-vm-size-and-quota)) |
| `SkuNotAvailable` | Size restricted or out of capacity in that region | Use `Standard_D8s_v5`, or recreate the resource group and network in another region |
| `[FAIL] Python 3.11 is required` from start.sh | Ubuntu 24.04 ships Python 3.12 | Install 3.11 and activate a 3.11 venv ([Step 7](#install-python-311-and-node)); do not change `target-version` |
| Chat takes 10-30 seconds | Expected on CPU | Use `tinyllama` for easier labs, add vCPUs, or [add a GPU](#optional-gpu-acceleration) |
| Chat takes over a minute or times out | Concurrent prompts or insufficient RAM | One member per lab at a time; check `free -h` and `htop` |
| `lscpu` shows no `avx2` | Unsuitable VM size | Resize to a Dasv5 or Dsv5 size |
| start.sh reports Ollama not reachable | Ollama service not running | `sudo systemctl status ollama`, then `sudo systemctl start ollama` |
| SSH to `100.x.y.z` fails or times out | Client not on the tailnet, VM deallocated, or node key expired | [Join WSL to the tailnet](#join-a-wsl-workstation-to-the-tailnet); `az vm start`; check `tailscale status` and key expiry |
| SSH to `100.x.y.z` hangs, but `tailscale status` shows the VM and `ping` works | WSL's MTU is too small for Tailscale, so large handshake packets are dropped | See [SSH hangs but ping works](#ssh-hangs-but-ping-works) |
| `Permission denied (publickey)` | Wrong key offered, key not authorized, or Tailscale SSH enabled | See [SSH permission denied](#ssh-permission-denied) |
| Pages load but login or chat fails | App opened via `100.x.y.z`; backend rejects that origin | Use the [SSH tunnel](#open-the-app-through-an-ssh-tunnel) and http://localhost:3000 |
| "Invalid credentials" for every user | Wrong origin, or database not seeded | See [Login fails for every user](#login-fails-for-every-user) |
| Port already in use | Previous run still alive | `./scripts/stop.sh`, then start again |
| `env: 'bash\r': No such file or directory` running a script | The file has Windows (CRLF) line endings, usually from copying it through a Windows editor | `sed -i 's/\r$//' <script>` (or `dos2unix <script>`), then run it again |
| Still being charged after "stopping" | VM stopped but not deallocated | `az vm deallocate`; confirm with `az vm list -d` |

#### SSH permission denied

The network path works but the VM rejected the key. Common causes: the client offers a different key than the one installed (`az vm create --generate-ssh-keys` installs `~/.ssh/id_rsa`, not an ed25519 key), the key is stored outside `~/.ssh` where SSH does not look by default, or Tailscale SSH is enabled.

1. Try the key Azure generated:

   ```bash
   ssh -i ~/.ssh/id_rsa azureuser@100.x.y.z
   ```

2. Otherwise, install your ed25519 public key via Run Command:

   ```bash
   PUB=$(cat ~/.ssh/id_ed25519.pub)
   az vm run-command invoke -g $RG -n $VM --command-id RunShellScript \
     --scripts "echo '$PUB' >> /home/azureuser/.ssh/authorized_keys"
   ```

3. If the key lives outside `~/.ssh`, pass it with `-i <path-to-private-key>` or move it into `~/.ssh` with mode `600`.
4. If SSH reports that key permissions are too open, the file is probably on a Windows-mounted drive (under `/mnt/c`). Copy it into the WSL filesystem:

   ```bash
   mkdir -p ~/.ssh && cp <path>/id_ed25519 <path>/id_ed25519.pub ~/.ssh/ && chmod 600 ~/.ssh/id_ed25519
   ```

5. Key errors only happen with Tailscale SSH off. If `ssh -v` shows `remote software version Tailscale`, keys aren't used at all; check the person is in the tailnet instead (see [Test SSH over Tailscale](#test-ssh-over-tailscale)).

To see which keys SSH offers and what the server accepts:

```bash
ssh -v azureuser@100.x.y.z 2>&1 | grep -E "Offering|Authentications|identity file"
```

#### SSH hangs but ping works

The tunnel is up, but SSH stalls during the handshake and never prompts or fails. `ssh -v` stops at `expecting SSH2_MSG_KEX_ECDH_REPLY`. This is not a firewall or public IP problem: traffic to `100.x.y.z` travels inside Tailscale, so the Azure NSG and your public IP play no part.

**Cause.** WSL's network adapter (`eth0`) can come up with an MTU of 1280 bytes, the same as `tailscale0`. Tailscale adds about 80 bytes to every packet, so full-size tunnel packets no longer fit and are dropped. Pings are small and get through; the SSH key exchange reply is large and does not.

1. Confirm it. Small pings succeed and large ones fail:

   ```bash
   ip link show eth0 | head -1                           # look for "mtu 1280"
   ping -c1 -M do -s 1100 100.x.y.z                      # succeeds
   ping -c1 -M do -s 1250 100.x.y.z                      # fails: packets this size are dropped
   ```

2. Fix it for the current session. The change is lost when WSL restarts:

   ```bash
   sudo ip link set dev tailscale0 mtu 1200
   ```

3. Make it permanent. Tailscale applies this MTU every time it starts:

   ```bash
   echo 'TS_DEBUG_MTU=1200' | sudo tee -a /etc/default/tailscaled
   sudo systemctl restart tailscaled
   ip link show tailscale0 | head -1                     # expect: mtu 1200
   ```

4. Test again: `ssh azureuser@100.x.y.z` should connect at once.

If 1200 still fails, find the largest ping size that works (`-s 1180`, `-s 1150`, …), add 28, and use that as the MTU.

#### Login fails for every user

1. **Check the origin first.** Open the app at http://localhost:3000 through the tunnel, not the `100.x.y.z` address. Via the Tailscale address, the CORS preflight (`OPTIONS /api/auth/login/`) fails with `400` and the UI shows a generic error:

   ```bash
   tail -n 30 ~/AIGoat/logs/backend.log
   ```

2. After switching, use a private window or hard refresh (Ctrl+Shift+R).
3. Only if the backend log shows the login `POST` itself failing (for example `401`) is the database at fault. Continue with [Reseeding the database](#reseeding-the-database).

If you need direct access by Tailscale address, add that origin to the backend's CORS settings; locate them with `grep -rn -i -E "cors|allow_origins" ~/AIGoat/app ~/AIGoat/config`.

#### Reseeding the database

By default the start script builds and runs the backend from `~/AIGoat/venv`. **On the VM:**

```bash
cd ~/AIGoat
./scripts/stop.sh
source ~/AIGoat/venv/bin/activate
python -c "import sqlalchemy; print(sqlalchemy.__version__)"   # must print a version, not an error
python -m scripts.seed                                          # expect: Seed completed successfully.
./scripts/start.sh
```

If the backend uses a different interpreter, identify it from the running process and run `<PYTHON> -m scripts.seed` from `~/AIGoat`:

```bash
PID=$(ss -tlnp | grep ':8000' | grep -o 'pid=[0-9]*' | cut -d= -f2)
tr '\0' ' ' < /proc/$PID/cmdline; echo    # for example /home/azureuser/AIGoat/venv/bin/python3 ...
```

If nothing is listening on 8000, install dependencies into your own venv and seed with it:

```bash
cd ~/AIGoat
source ~/aigoat-venv/bin/activate
pip install -r requirements.txt
python -m scripts.seed
```

| Command | Effect |
| --- | --- |
| `python -m scripts.seed` | Full run: resets the five default accounts' passwords, recreates shop data, **deletes all CTF attempts**, adds 6-8 random orders per demo user |
| `python -m scripts.seed --sync-challenges` | Updates challenge text and keeps attempts; use once members have progress |
| `python -m scripts.seed --sync-support` | Refreshes support tickets only |

> [!NOTE]
> Always run the seed from `~/AIGoat` so it writes to the database the backend reads. If the start script reports `Database already has required data` and login still fails, the cause is the browser origin, not the database; check the request URL in DevTools.

#### Locked out by UFW

Disable the firewall without SSH, from your workstation:

```bash
az vm run-command invoke -g $RG -n $VM --command-id RunShellScript --scripts "ufw disable"
```

### Optional: GPU acceleration

A GPU brings replies down to 1-3 seconds, but nothing in this runbook requires one.

| Option | Reply speed | Cost | Considerations |
| --- | --- | --- | --- |
| Pay-as-you-go subscription with A10 quota (`Standard NVADSA10v5 Family`, for example `Standard_NV18ads_A10_v5`) | 1-3 s | Credits | Region availability varies; requires NVIDIA's GRID driver; confirm Ollama uses the GPU slice |
| Google Colab (see `colab_notebooks/AIGoat_Colab.md` in the AIGoat repo) | 1-3 s | Free tier | Sessions time out and reset; each user runs their own notebook |
| Local install on Apple Silicon or an NVIDIA laptop | 1-3 s | Free | Needs 16 GB+ RAM; setup is repeated per machine |
| On-premises hypervisor VM (for example Proxmox), CPU only | 10-30 s | Free | Same speed as this VM without cloud spend; set the CPU type to `host` |

To switch an existing VM to a GPU:

1. Resize it to a GPU size.
2. Install the NVIDIA driver (`sudo ubuntu-drivers install` on NC-series; NVIDIA's GRID driver on NV A10 v5 sizes).
3. Reboot and run `nvidia-smi`.
4. Restart Ollama with `sudo systemctl restart ollama`. `ollama ps` should report `GPU` instead of `CPU`.

GPU families are normally blocked on free-trial subscriptions until you upgrade to pay-as-you-go. CPU reply speed depends on core count and AVX2 support; a smaller model such as `tinyllama` (set `ollama.model` in `config/config.yml`) is much faster, but exploits that work on Mistral may behave differently.

[↑ Back to top](#contents)
