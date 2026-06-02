# Deploying Meridian Financial Analyst Agent on AWS EC2

This is a **complete, beginner-friendly, copy-paste guide** to deploy the Meridian
Financial Analyst Agent (FastAPI + LangChain) on a single AWS EC2 Ubuntu server,
served to the public internet through Nginx and kept alive by `systemd`.

follow this kink for the Gemini steps: https://gemini.google.com/share/2ea0597b8333


By the end you will have the app running 24/7 at `http://<YOUR-EC2-PUBLIC-IP>/`.



---

## 0. What we are building

```
                      ┌──────────────────────── EC2 Ubuntu 24.04 ───────────────────────┐
   Browser  ──HTTP──▶ │  Nginx (port 80)  ──reverse proxy──▶  Uvicorn / FastAPI (8000)  │
   (you)              │     ▲                                   ▲   (managed by systemd) │
                      │     └── WebSocket upgrade for /ws/chat ─┘                        │
                      └──────────────────────────────────────────────────────────────────┘
```

- **Nginx** listens on the public port 80 and forwards requests to the app.
- **Uvicorn** runs the FastAPI app internally on `127.0.0.1:8000` (not exposed directly).
- **systemd** starts the app on boot and restarts it if it crashes.
- The chat uses a **WebSocket** (`/ws/chat`), so Nginx must be configured to upgrade
  WebSocket connections (covered in Step 11).

**Server spec used in this guide:**

| Setting        | Value                          |
| -------------- | ------------------------------ |
| Instance type  | `t3.medium` (2 vCPU, 4 GB RAM) |
| OS / AMI       | Ubuntu Server 24.04 LTS        |
| Storage        | 20 GB, gp3                     |
| Python         | 3.12.x (ships with Ubuntu 24.04) |

> 💡 **Why t3.medium?** The app loads a FAISS vector store and LangChain into memory.
> `t3.micro`/`small` (1 GB / 2 GB RAM) can run out of memory while building the
> vector index on first run. 4 GB gives comfortable headroom.

---

## 1. Prerequisites

Before starting, make sure you have:

1. An **AWS account** with access to the EC2 console.
2. An **OpenAI API key** (`sk-...`) and a **Tavily API key** (`tvly-...`).
3. An **SSH key pair** (created during instance launch below) to log in to the server.
4. Basic comfort with a terminal. Every command is provided — just copy, paste, Enter.

---

## 2. Launch the EC2 instance

1. Sign in to the **AWS Console** → search **EC2** → click **Launch instance**.
2. **Name:** `meridian-agent`
3. **Application and OS Images (AMI):** choose **Ubuntu**, then select
   **Ubuntu Server 24.04 LTS (HVM), SSD Volume Type** (64-bit x86).
4. **Instance type:** select **`t3.medium`**.
5. **Key pair (login):**
   - Click **Create new key pair**.
   - Name it `meridian-key`, type **RSA**, format **.pem** (or **.ppk** if you use PuTTY on Windows).
   - Click **Create key pair** — the file downloads to your computer. **Keep it safe; you cannot download it again.**
6. **Network settings** → click **Edit**, then under **Firewall (security groups)** create a
   security group allowing the following **inbound** rules:

   | Type   | Protocol | Port | Source           | Why                         |
   | ------ | -------- | ---- | ---------------- | --------------------------- |
   | SSH    | TCP      | 22   | My IP            | So you can log in           |
   | HTTP   | TCP      | 80   | Anywhere (0.0.0.0/0) | So the public can reach the app |
   | HTTPS  | TCP      | 443  | Anywhere (0.0.0.0/0) | For future TLS (optional now) |

   > ⚠️ **This AWS Security Group is separate from the server's UFW firewall (Step 6).**
   > Both must allow the traffic. If the page won't load later, 9 times out of 10 it is
   > a missing Security Group rule here.

7. **Configure storage:** set the root volume to **20 GiB**, type **gp3**.
8. Click **Launch instance**.
9. Wait until **Instance state = Running** and note the **Public IPv4 address**
   (e.g. `13.232.45.67`). You will use this throughout.

---

## 3. Connect to the server via SSH

On your local machine, open a terminal (PowerShell, Windows Terminal, macOS Terminal, or Linux shell).

```bash
# Move to where your key file is, then restrict its permissions (Linux/macOS):
chmod 400 meridian-key.pem

# Connect (replace with YOUR public IP):
ssh -i meridian-key.pem ubuntu@<YOUR-EC2-PUBLIC-IP>
```

- The default username for Ubuntu AMIs is **`ubuntu`**.
- Type **`yes`** when asked to trust the host fingerprint the first time.

> **Windows users:** if you used a `.ppk` key, connect with PuTTY instead, or use the
> `.pem` directly with the built-in OpenSSH client as shown above.

You are now logged in to the server. Every command below runs **on the EC2 server**.

---

## 4. Update and upgrade system packages

Always start with a fully patched system:

```bash
sudo apt update && sudo apt upgrade -y
```

- `apt update` refreshes the list of available packages.
- `apt upgrade -y` installs the latest versions (`-y` auto-confirms).

If you are told a reboot is required, reboot and reconnect:

```bash
sudo reboot
# wait ~30 seconds, then SSH back in
```

---

## 5. Install Python 3.12 and required system libraries

Ubuntu 24.04 **already ships Python 3.12**, so we only need the virtual-environment
and dev tooling plus our service packages.

```bash
sudo apt install -y \
    python3.12 python3.12-venv python3.12-dev python3-pip \
    git tmux nginx certbot python3-certbot-nginx ufw \
    build-essential curl
```

What each package is for:

| Package(s)                         | Purpose                                                        |
| ---------------------------------- | ------------------------------------------------------------- |
| `python3.12`, `-venv`, `-dev`      | The Python runtime + ability to create virtual environments   |
| `python3-pip`                      | Python package installer                                      |
| `git`                              | Clone the project from GitHub                                 |
| `tmux`                             | Keep a terminal session alive (useful for manual testing)     |
| `nginx`                            | Web server / reverse proxy facing the internet                |
| `certbot`, `python3-certbot-nginx` | Free HTTPS/TLS certificates (only usable with a domain name)  |
| `ufw`                              | Simple host firewall                                          |
| `build-essential`                  | Compilers, in case a Python package needs to build from source |
| `curl`                             | Test HTTP endpoints from the command line                     |

Confirm Python is present:

```bash
python3.12 --version
# Expected: Python 3.12.x
```

---

## 6. Configure the UFW firewall (on the server)

This is the **server-level** firewall (in addition to the AWS Security Group from Step 2).

```bash
sudo ufw allow OpenSSH      # keep SSH (port 22) open — do this FIRST
sudo ufw allow 'Nginx Full' # opens ports 80 (HTTP) and 443 (HTTPS)
sudo ufw --force enable     # turn the firewall on
sudo ufw status verbose     # verify the rules
```

> ⚠️ **Always allow OpenSSH before enabling UFW**, or you will lock yourself out of the server.

---

## 7. Clone the project

```bash
cd ~
git clone https://github.com/prashant9501/meridian-wealth.git
cd meridian-wealth
```

You are now inside the project directory: `/home/ubuntu/meridian-wealth`.

Quick look at what's here:

```bash
ls -la
# You should see: app.py, requirements.txt, config.yaml, src/, frontend/, data/, ...
```

---

## 8. Verify the Python version inside the project

Make sure the project will use Python 3.12:

```bash
python3.12 --version
# Expected: Python 3.12.x
```

If this does not say `3.12.x`, stop and re-check Step 5 before continuing.

---

## 9. Create and activate a virtual environment

We isolate the project's Python packages in a `.venv` folder using **Python 3.12**:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
```

Your prompt should now start with `(.venv)`. Confirm the venv uses 3.12:

```bash
python --version
# Expected: Python 3.12.x
```

Upgrade pip inside the venv:

```bash
pip install --upgrade pip
```

---

## 10. Install the Python dependencies

```bash
pip install -r requirements.txt
```

Then install the **production-grade Uvicorn** (bundles `websockets`, `httptools`,
`uvloop`). **This is required for the chat WebSocket (`/ws/chat`) to work:**

```bash
pip install "uvicorn[standard]"
```

> This step can take a few minutes (LangChain, FAISS, pandas are large).

---

## 11. Configure environment variables (API keys)

The app reads its API keys from a `.env` file in the project root.

```bash
nano .env
```

Paste the following, replacing the placeholder values with your **real** keys:

```env
OPENAI_API_KEY=sk-your_actual_openai_api_key_here
TAVILY_API_KEY=tvly-your_actual_tavily_api_key_here
```

Save and exit nano: press **`Ctrl + O`**, then **`Enter`**, then **`Ctrl + X`**.

> 🔒 The `.env` file is git-ignored and must **never** be committed to GitHub.

Verify it was written (keys will be visible — keep this screen private):

```bash
cat .env
```

---

## 12. (Optional but recommended) Test-run the app manually

Before wiring up systemd, confirm the app starts. We use **tmux** so the app keeps
running even if your SSH connection drops.

```bash
tmux new -s meridian          # start a named tmux session
source .venv/bin/activate      # activate the venv inside tmux
uvicorn app:app --host 127.0.0.1 --port 8000
```

In a **second** SSH session (or detach tmux with `Ctrl + B` then `D`), test it:

```bash
curl http://127.0.0.1:8000/health
# Expect a JSON health report
```

> ⏳ **First run is slow:** the very first request builds the FAISS vector index from
> the policy PDFs using OpenAI embeddings. This can take 1–3 minutes and requires a
> valid `OPENAI_API_KEY`. Subsequent starts load the saved index instantly.

When satisfied, stop the manual run with **`Ctrl + C`**, then kill the tmux session:

```bash
exit            # leave tmux
tmux kill-session -t meridian
```

We will now run the app properly as a background service.

---

## 13. Create the systemd service (run the app 24/7)

`systemd` will start the app on boot and restart it automatically if it crashes.

Create the service file:

```bash
sudo nano /etc/systemd/system/meridian.service
```

Paste this exactly:

```ini
[Unit]
Description=Meridian Financial Analyst Agent (FastAPI/Uvicorn)
After=network.target

[Service]
User=ubuntu
Group=ubuntu
WorkingDirectory=/home/ubuntu/meridian-wealth
ExecStart=/home/ubuntu/meridian-wealth/.venv/bin/uvicorn app:app --host 127.0.0.1 --port 8000
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

Save and exit (**`Ctrl + O`**, **`Enter`**, **`Ctrl + X`**).

> ℹ️ The app loads keys from `.env` automatically via `python-dotenv`, and because
> `WorkingDirectory` points at the project root, the `.env` file is found correctly.

### Register, start, and check the service

```bash
sudo systemctl daemon-reload          # tell systemd about the new file
sudo systemctl enable meridian        # start automatically on every boot
sudo systemctl start meridian         # start it now
sudo systemctl status meridian        # check it is running
```

A healthy service shows **`Active: active (running)`** in green.
Press **`q`** to exit the status view.

> ⏳ Remember: the **first** request after starting may take 1–3 minutes while the
> vector index builds. Watch the logs (next step) to see progress.

---

## 14. View the application logs

All app output (including errors and the vector-index build messages) goes to the
systemd journal:

```bash
# Live, follow new log lines (Ctrl + C to stop watching):
sudo journalctl -u meridian -f

# Last 100 lines:
sudo journalctl -u meridian -n 100 --no-pager

# Logs since the last boot:
sudo journalctl -u meridian -b
```

> The lines `incorrect startxref pointer(1)` during startup are harmless PDF-parsing
> warnings from the policy documents — not errors.

---

## 15. Configure Nginx as a reverse proxy (with WebSocket support)

Now expose the app to the internet on port 80.

Create an Nginx site config:

```bash
sudo nano /etc/nginx/sites-available/meridian
```

Paste this:

```nginx
server {
    listen 80;
    server_name _;   # matches any hostname / the public IP

    client_max_body_size 10M;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;

        proxy_set_header Host              $host;
        proxy_set_header X-Real-IP         $remote_addr;
        proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # --- WebSocket support (REQUIRED for the /ws/chat streaming chat) ---
        proxy_set_header Upgrade    $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_read_timeout 300s;     # keep long-lived agent streams open
    }
}
```

Save and exit. Then enable the site and disable the default one:

```bash
# Enable our site:
sudo ln -s /etc/nginx/sites-available/meridian /etc/nginx/sites-enabled/

# Remove the default placeholder site so it doesn't shadow ours:
sudo rm -f /etc/nginx/sites-enabled/default

# Test the Nginx config for syntax errors:
sudo nginx -t

# Apply the changes:
sudo systemctl restart nginx
```

`sudo nginx -t` must report **`syntax is ok`** and **`test is successful`** before you restart.

---

## 16. Open the app in your browser 🎉

In your browser, go to:

```
http://<YOUR-EC2-PUBLIC-IP>/
```

Example: `http://13.232.45.67/`

### ⚠️ "It opened as `https://` and shows an error!"

If your browser **auto-changes the address to `https://`** (many browsers force HTTPS,
and some remember it via HSTS), you'll get a connection/security error — because we
have **not installed a TLS certificate** (that needs a real domain name, not a bare IP).

**The fix is simple:** click the address bar and **delete the `s` from `https`** so it
reads `http://<YOUR-EC2-PUBLIC-IP>/`, then press Enter. **It works!** ✅

Try all the pages:

- `http://<IP>/` — Home
- `http://<IP>/chat` — streaming chat workspace
- `http://<IP>/data` — data explorer
- `http://<IP>/agent_info` — agent tools & config
- `http://<IP>/health` — JSON health check

---

## 17. (Optional) Enable real HTTPS with a domain name

A bare IP cannot get a trusted certificate. If you own a domain (e.g. `meridian.example.com`):

1. In your DNS provider, create an **A record** pointing the domain to your EC2 public IP.
2. Edit the Nginx config and set `server_name meridian.example.com;` (replace the `_`).
3. Reload Nginx: `sudo systemctl reload nginx`.
4. Obtain and install a free Let's Encrypt certificate (Certbot edits Nginx for you):

   ```bash
   sudo certbot --nginx -d meridian.example.com
   ```

5. Certbot also sets up automatic renewal. Test it:

   ```bash
   sudo certbot renew --dry-run
   ```

Now `https://meridian.example.com/` works with a valid padlock.

---

## 18. Updating the app after code changes

When you push new code to GitHub, update the server like this:

```bash
cd ~/meridian-wealth
git pull
source .venv/bin/activate
pip install -r requirements.txt      # only if dependencies changed
sudo systemctl restart meridian      # restart the app
sudo journalctl -u meridian -f       # watch it come back up
```

---

## 19. Troubleshooting

| Symptom | Likely cause & fix |
| ------- | ------------------ |
| Browser can't connect at all | AWS **Security Group** missing the port-80 inbound rule (Step 2), or UFW not allowing Nginx (Step 6). |
| Browser forces `https://` and errors | No TLS on a bare IP — **remove the `s`** and use `http://` (Step 16), or set up a domain (Step 17). |
| `502 Bad Gateway` from Nginx | The app isn't running. Check `sudo systemctl status meridian` and `sudo journalctl -u meridian -n 50`. |
| Chat connects but never responds | WebSocket not upgrading — confirm the `Upgrade`/`Connection` headers in the Nginx config (Step 15) and that you installed `uvicorn[standard]` (Step 10). |
| `500` error / "Missing critical configuration keys" | `.env` missing or has placeholder keys. Re-check Step 11, then `sudo systemctl restart meridian`. |
| First request hangs for minutes | Normal on first run — the FAISS index is being built. Watch `journalctl -u meridian -f`. |
| App killed / out of memory | Use at least `t3.medium` (4 GB). Check with `free -h`. |
| `nginx -t` fails | A typo in the site config. Re-open `/etc/nginx/sites-available/meridian` and fix. |

---

## 20. Handy command cheat sheet

```bash
# Service control
sudo systemctl start meridian        # start
sudo systemctl stop meridian         # stop
sudo systemctl restart meridian      # restart
sudo systemctl status meridian       # status

# Logs
sudo journalctl -u meridian -f       # follow live
sudo journalctl -u meridian -n 100   # last 100 lines

# Nginx
sudo nginx -t                        # test config
sudo systemctl restart nginx         # apply config
sudo systemctl status nginx          # nginx status

# Firewall
sudo ufw status verbose              # show rules

# System
free -h                              # memory usage
df -h                                # disk usage
htop                                 # live processes (sudo apt install htop)
```

---

### You're done!

Your Meridian Financial Analyst Agent is now running on AWS EC2, managed by systemd,
and served to the world through Nginx. 🚀
