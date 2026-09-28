# Setting up the LLM server on Oracle Cloud (free)

Nazar uses a language model (LLM) for two jobs: writing a one-line **narrative statement** for each group of articles, and writing the **intelligence brief**. The model runs on a free computer in Oracle's cloud, not on your laptop. Your laptop talks to it through a private, encrypted connection.

```
 YOUR LAPTOP                                        ORACLE CLOUD (free VM)
 ┌──────────────────────────┐   SSH tunnel    ┌──────────────────────────────┐
 │ Nazar                    │  (encrypted,    │ Ollama  (runs the LLM)       │
 │   asks 127.0.0.1:11434 ──┼──── private) ───┼──> 127.0.0.1:11434           │
 │                          │                 │ qwen2.5 3b + 7b models       │
 └──────────────────────────┘                 └──────────────────────────────┘
```

Nazar thinks the model is on your own machine (`127.0.0.1` means "this computer"). The **SSH tunnel** quietly forwards those requests to the Oracle server and brings the answers back. The server never needs to be open to the internet.

**Time needed:** about 45–60 minutes, most of it waiting for sign-up checks and model downloads.

> **PowerShell or Command Prompt?** Commands for your laptop are shown for both. Check the prompt: **PowerShell** shows `PS C:\Users\you>`, **Command Prompt (CMD)** shows `C:\Users\you>`. `$HOME` and `Get-Content` only work in PowerShell; in CMD use `%USERPROFILE%` and `type`.

---

## Step 1: Create an Oracle Cloud account

1. Go to **https://www.oracle.com/cloud/free/** and click **Start for free**.
2. Fill in your details. Oracle asks for a **card for identity verification**. It may place a small temporary hold, but *Always Free* resources don't cost anything.
3. **Choose your "home region" carefully. You can't change it later**, and free machines can only be created there. Pick one near you (for India: *India West (Mumbai)* or *India South (Hyderabad)*). Popular regions sometimes run out of free machines; see "Out of capacity" in Troubleshooting.
4. Finish sign-up and log in to the **Oracle Cloud Console**.

> Oracle's free-tier terms change over time. Check the current *Always Free* limits on their site. At the time of writing, the free ARM allowance is 4 CPU cores and 24 GB of memory in total.

## Step 2: Make an SSH key on your laptop

An **SSH key** is a pair of files that acts like a password you never type. The **public** half goes to Oracle; the **private** half stays on your laptop and must never be shared.

Run one of these. If the `.ssh` folder doesn't exist yet, create it first: `mkdir $HOME\.ssh` in PowerShell, `mkdir %USERPROFILE%\.ssh` in CMD.

```powershell
# PowerShell
ssh-keygen -t ed25519 -f $HOME\.ssh\nazar_oracle
```

```cmd
:: Command Prompt
ssh-keygen -t ed25519 -f %USERPROFILE%\.ssh\nazar_oracle
```

Press Enter twice to skip the passphrase, or set one if you prefer. This creates two files:

- `C:\Users\<you>\.ssh\nazar_oracle`: **private key** (keep secret)
- `C:\Users\<you>\.ssh\nazar_oracle.pub`: **public key** (goes to Oracle)

Show the public key so you can copy it (one line starting with `ssh-ed25519`):

```powershell
# PowerShell
Get-Content $HOME\.ssh\nazar_oracle.pub
```

```cmd
:: Command Prompt
type %USERPROFILE%\.ssh\nazar_oracle.pub
```

## Step 3: Create the virtual machine

In the Oracle Console:

1. Menu (☰) → **Compute** → **Instances** → **Create instance**.
2. **Name:** `nazar-llm`.
3. **Image and shape** → **Edit**:
   - **Image:** click *Change image* → **Canonical Ubuntu** → version **22.04** or **24.04**.
   - **Shape:** click *Change shape* → **Ampere** → **VM.Standard.A1.Flex**. Set **OCPUs = 4** and **Memory = 24 GB**. It should show an *Always Free-eligible* label.
4. **Networking:** keep the defaults (it creates a network for you). Make sure **Assign a public IPv4 address** is **Yes**.
5. **Add SSH keys:** choose **Paste public keys** and paste the line you copied in Step 2.
6. **Boot volume:** the default size is fine.
7. Click **Create**. Wait until the status turns **RUNNING** (a minute or two), then copy the **Public IP address** from the instance page. The rest of this guide calls it `<IP>`.

## Step 4: Connect to the server

```powershell
# PowerShell
ssh -i $HOME\.ssh\nazar_oracle ubuntu@<IP>
```

```cmd
:: Command Prompt
ssh -i %USERPROFILE%\.ssh\nazar_oracle ubuntu@<IP>
```

The first time, it asks whether you trust the server: type `yes`. You're now "inside" the Oracle machine; the prompt looks like `ubuntu@nazar-llm:~$`.

## Step 5: Install Ollama and the models (on the server)

Run these **on the server** (inside the SSH session):

```bash
# update the system
sudo apt update && sudo apt upgrade -y

# install Ollama (it installs itself as a background service)
curl -fsSL https://ollama.com/install.sh | sh

# check it is running
systemctl status ollama --no-pager

# download the two models Nazar uses (about 2 GB + 4.7 GB)
ollama pull qwen2.5:3b-instruct
ollama pull qwen2.5:7b-instruct

# quick test (the answer appears slowly: this machine has no GPU)
ollama run qwen2.5:3b-instruct "Say hello in Hindi in one short sentence."
```

What each model is for:
- **qwen2.5:3b-instruct** (smaller, faster): writes the narrative statements, one short answer per narrative.
- **qwen2.5:7b-instruct** (bigger, better): writes the intelligence brief, one long answer.

Type `exit` to leave the server.

> **Don't open port 11434 in Oracle's firewall ("security list").** Ollama has no password. By default it only listens to requests from the server itself, and the SSH tunnel is how your laptop reaches it safely.

## Step 6: Open the tunnel (every time you use the LLM)

Open a **new terminal window** and run the command below. **Keep this window open** while you use Nazar: closing it closes the tunnel.

```powershell
# PowerShell
ssh -i $HOME\.ssh\nazar_oracle -N -o ServerAliveInterval=60 -L 11434:127.0.0.1:11434 ubuntu@<IP>
```

```cmd
:: Command Prompt
ssh -i %USERPROFILE%\.ssh\nazar_oracle -N -o ServerAliveInterval=60 -L 11434:127.0.0.1:11434 ubuntu@<IP>
```

- `-L 11434:127.0.0.1:11434` means "my port 11434 → the server's port 11434".
- `-N` means "don't open a shell, just forward".
- `ServerAliveInterval=60` keeps the connection from dropping when idle.

It looks like nothing happens. That's normal: the window just sits there while the tunnel is open.

**Check it works** (in another window; `curl.exe` in PowerShell, plain `curl` in CMD):

```powershell
curl.exe http://127.0.0.1:11434/api/tags
```

You should see a list with both qwen2.5 models. In Nazar, the top-right status turns to **LLM connected**.

### Optional: a shortcut

Create the file `C:\Users\<you>\.ssh\config` (no extension) with:

```
Host nazar-llm
    HostName <IP>
    User ubuntu
    IdentityFile ~/.ssh/nazar_oracle
    LocalForward 11434 127.0.0.1:11434
    ServerAliveInterval 60
```

Then the tunnel is just `ssh -N nazar-llm`, and `ssh nazar-llm` logs you in.

## Step 7: Use it in Nazar

Nothing to change: Nazar already looks for the LLM at `http://127.0.0.1:11434` (the `OLLAMA_URL` setting in `.env`). With the tunnel open:

- **Run a monitor.** Narrative titles become written statements, and the progress shows "Naming narrative 3/9".
- **On a completed monitor, open Intelligence brief → Generate brief.**

**How long it takes:** this server has 4 ARM CPU cores and no GPU, so the LLM writes slowly, roughly a few words per second for the 7b model. Expect about 10–30 seconds per narrative title and a few minutes for a brief. These are estimates; the Nazar log records the real times. Every answer is saved, so asking the same thing again is instant.

---

## Troubleshooting

| Problem | What it means | Fix |
|---|---|---|
| **"Out of capacity for shape VM.Standard.A1.Flex"** | Oracle's free ARM machines in your region are all in use right now | Try again later (capacity frees up over the day). If your region has several *availability domains*, try another one in the Create screen. As a temporary step, create it with 2 OCPU / 12 GB and resize later. |
| **"Permission denied (publickey)"** | Wrong key or wrong username | Username must be `ubuntu` for Ubuntu images. Check the `-i` path points at the private key whose `.pub` you pasted. |
| **"Saving key … failed: No such file or directory"** | The `.ssh` folder is missing, or `$HOME` was used in Command Prompt | In CMD use `%USERPROFILE%` (see Step 2), or create the folder first |
| **"UNPROTECTED PRIVATE KEY FILE"** (Windows) | Windows lets other accounts read the key | PowerShell: `icacls $HOME\.ssh\nazar_oracle /inheritance:r /grant:r "$($env:USERNAME):(R)"` · CMD: `icacls %USERPROFILE%\.ssh\nazar_oracle /inheritance:r /grant:r "%USERNAME%:(R)"` |
| **"bind: Address already in use"** when starting the tunnel | Something on your laptop already uses port 11434 (another tunnel, or a local Ollama) | Close the other tunnel window, or quit local Ollama. |
| Nazar still shows **LLM offline** | Tunnel not running, or Ollama stopped on the server | Check the tunnel window is open; on the server run `systemctl status ollama` and `sudo systemctl restart ollama`. |
| Tunnel keeps dropping | Idle connection closed by the network | Keep `-o ServerAliveInterval=60`; reopen the tunnel. |

## Good to know

- **Idle machines can be reclaimed.** Oracle's policy allows it to reclaim *Always Free* machines that sit almost completely idle for about a week. Check their current policy. If it happens, repeat Steps 3–5; your laptop key can be reused.
- **Stay within Always Free.** Only create resources marked *Always Free-eligible*, and don't upgrade the account to "Pay As You Go" unless you intend to pay.
- **Stopping vs terminating.** *Stop* pauses the machine and keeps its disk and models. *Terminate* deletes it.
