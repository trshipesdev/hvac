# Deploying to Oracle Cloud (for continuous Resideo polling)

This app runs fine entirely on your laptop via `./run.sh` — that's the
default, and it's all you need while Resideo API access is still pending.
The one thing your laptop can't do is poll continuously: the Resideo sync
job is a background task inside the same process `run.sh` starts, so it
only runs while your Mac is on and the app is running.

Once you're actually connected to a live Resideo API and want real 24/7
polling (so you don't lose thermostat history every time you close your
laptop), move the backend to an always-on box. Oracle Cloud's **Always
Free** tier includes an ARM (Ampere A1) compute instance that's genuinely
free forever and plenty for this workload — no credit card charges as long
as you stay within the free-tier shape limits.

This is a deliberate, separate step from the rest of the setup — do this
when you're ready to move off your laptop, not before.

## 1. Create the instance

1. Sign up for an Oracle Cloud account (requires a card for identity
   verification, but the Always Free resources genuinely don't charge it).
2. Create a Compute instance:
   - **Shape:** `VM.Standard.A1.Flex` (Ampere ARM) — up to 4 OCPUs / 24 GB
     RAM is included free; this app needs a fraction of that.
   - **Image:** Ubuntu 22.04 or 24.04 LTS (ARM build).
   - Generate or upload an SSH key pair during creation — you'll need it to
     connect.
3. Note the instance's public IP address once it's running.

## 2. Open the firewall

Oracle Cloud has two layers to open: the **Security List** (or Network
Security Group) on the VCN, and the OS firewall on the instance itself.

- In the OCI console, add ingress rules to the subnet's security list for
  the ports you need (e.g. `8000` for the API, `443`/`80` if you put a
  reverse proxy in front).
- On the instance itself (Ubuntu ships with iptables rules OCI pre-applies):
  ```bash
  sudo iptables -I INPUT -p tcp --dport 8000 -j ACCEPT
  sudo netfilter-persistent save   # if installed, to persist across reboots
  ```

## 3. Install prerequisites on the instance

```bash
ssh ubuntu@<your-instance-ip>
sudo apt update
sudo apt install -y python3.11 python3.11-venv mongodb nodejs npm git
sudo npm install -g yarn
```

(Package availability varies by Ubuntu version — use whatever Python 3.10+
and MongoDB packages your chosen image provides, or install MongoDB from
[its own apt repo](https://www.mongodb.com/docs/manual/tutorial/install-mongodb-on-ubuntu/)
for a more current version.)

## 4. Clone and set up the app

```bash
git clone https://github.com/trshipesdev/hvac.git
cd hvac
./setup.sh
# fill in backend/.env with your real credentials
```

## 5. Run it as a systemd service (instead of `run.sh`)

`run.sh` is designed for interactive local use (it opens a browser, expects
Ctrl-C). On a server, run the backend directly as a service so it survives
reboots and stays up unattended:

```ini
# /etc/systemd/system/hvac-backend.service
[Unit]
Description=HVAC Efficiency Analyzer backend
After=network.target mongodb.service

[Service]
WorkingDirectory=/home/ubuntu/hvac/backend
ExecStart=/home/ubuntu/hvac/backend/venv/bin/uvicorn server:app --host 0.0.0.0 --port 8000
Restart=on-failure
User=ubuntu

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now hvac-backend
sudo systemctl status hvac-backend
```

The APScheduler job inside the FastAPI process (the one that polls Resideo
every 15 minutes) now runs continuously as long as the service is up —
which systemd guarantees across reboots via `Restart=on-failure` and
`enable`.

For the frontend, either build a static production bundle (`yarn build` in
`frontend/`) and serve it with nginx/Caddy, or just run the backend on the
server and keep using the app from your laptop's browser pointed at
`http://<instance-ip>:8000` — the polling continuity is what actually
matters here, not where you view the dashboard from.

## 6. Migrate your existing data (optional)

If you've already been running locally and want to bring your history over
rather than starting fresh:

```bash
# On your Mac
mongodump --db hvac --archive=hvac-backup.archive

# Copy to the server
scp hvac-backup.archive ubuntu@<your-instance-ip>:~

# On the server
mongorestore --db hvac --archive=~/hvac-backup.archive
```

## Security notes

- Don't expose MongoDB's port (27017) to the public internet — it should
  only be reachable from the backend on the same instance (default bind is
  `127.0.0.1`, keep it that way).
- Keep `backend/.env` off the repo and readable only by the service user
  (`chmod 600`).
- If you do put the API on the public internet long-term, put it behind a
  reverse proxy with TLS (Caddy makes this closer to one-line than nginx)
  rather than serving plain HTTP on a raw port.
