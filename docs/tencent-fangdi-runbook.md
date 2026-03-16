# Tencent Cloud Fangdi Runbook

Assumption: Tencent Cloud Lighthouse or CVM running Ubuntu 22.04/24.04 with SSH access.

## 1. Goal

Turn the server into a remote browser machine:

- OpenClaw runs the schedule
- A persistent desktop session runs Chrome
- You only remote in briefly to unlock the site when needed
- The browser keeps running on the server after you disconnect

## 2. One-time server setup

### 2.1 Install desktop and remote desktop

```bash
sudo apt update
sudo apt install -y xfce4 xfce4-goodies xrdp dbus-x11 xorg fonts-noto-cjk
echo xfce4-session > ~/.xsession
sudo adduser xrdp ssl-cert
sudo systemctl enable xrdp
sudo systemctl restart xrdp
```

Open port `3389` in:

- Tencent Cloud security group
- local firewall if enabled

If you use `ufw`:

```bash
sudo ufw allow 3389/tcp
```

Recommended: restrict `3389` to your own IP only.

### 2.2 Install Chrome

```bash
cd /tmp
wget https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb
sudo apt install -y ./google-chrome-stable_current_amd64.deb
```

### 2.3 Install Node and Python tools

```bash
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install -y nodejs python3-venv python3-pip git
```

### 2.4 Pull this project and install deps

```bash
mkdir -p ~/work
cd ~/work
git clone <your-repo-url> fangdi-data
cd fangdi-data
npm install --registry=https://registry.npmmirror.com
python3 -m venv .venv
. .venv/bin/activate
pip install -U pip
pip install ddddocr opencv-python-headless numpy -i https://pypi.tuna.tsinghua.edu.cn/simple
```

## 3. Browser profile

Create one dedicated Chrome profile for Fangdi:

```bash
mkdir -p ~/chrome-fangdi
```

Launch Chrome with the dedicated profile:

```bash
google-chrome \
  --user-data-dir=$HOME/chrome-fangdi \
  --no-first-run \
  --disable-dev-shm-usage
```

Use this same profile every day. Do not mix it with other browsing.

## 4. Daily workflow

### 4.1 Connect to the server desktop

Use Microsoft Remote Desktop or any RDP client to connect to:

- `SERVER_IP:3389`

### 4.2 Unlock the website manually

Inside the remote desktop:

1. Open Chrome with the Fangdi profile
2. Open the Fangdi query page
3. Confirm the site is usable
4. Run one manual query successfully

At this point the browser session is ready.

### 4.3 Start the data job

You have two options:

- Trigger the job from OpenClaw
- Or run it by SSH on the server

The worker should:

- reuse the existing browser session/profile
- run queries sequentially
- write every successful query result immediately
- stop and alert if failure rate spikes

### 4.4 Disconnect without logging out

Important:

- close the RDP window or disconnect
- do **not** click logout
- do **not** kill Chrome

The browser should keep running on the server.

## 5. Runtime rules

To stay stable:

- use one browser profile only
- use one query worker only
- do not run headless
- do not run high concurrency
- add random sleep between queries
- checkpoint every query

## 6. Session recovery

If the job starts failing:

- reconnect to the server desktop
- check whether Fangdi fell back to a blank page or challenge page
- recover the query page manually
- continue the worker from the unfinished queue

## 7. OpenClaw integration

Recommended task split:

1. `precheck`
   - verify browser process exists
   - verify Chrome profile path exists

2. `run_counts`
   - execute the count-query worker

3. `aggregate`
   - summarize `district x plate x listing_age_bucket`

4. `build_pack`
   - generate the content pack for posting

5. `notify`
   - send the output path and failure summary to you

## 8. First PoC

Before running the full daily job, test only:

- 1 district
- 3 plates
- all listing-age buckets

If that passes cleanly for 20-30 queries, then expand to the full matrix.

## 9. Practical warning

Tencent Cloud uses a data-center IP. The site may treat it more strictly than a normal residential connection.

So first validate:

- can you enter the site stably from the cloud desktop
- can you do 20-30 manual queries in a row
- does the session survive after disconnecting RDP

If yes, then this server can be your main runner.
