# Steps
---
## 1️⃣ Connect Ubuntu Desktop to WiFi

I have confirmed this setup guide works for Ubuntu Desktop LTS (https://ubuntu.com/download/desktop)
On Ubuntu Desktop:

1. Open **Settings → Network → Wi-Fi**
2. Select your campus network (e.g., Campus WiFi)
3. Complete authentications

Verify connection:

```bash
ip a
```

Look for your wireless interface (likely `wlp0s20f3` or something similar).

You should see something like:

```
inet xxx.xxx.xxx.xxx/xx
```

That `xxx.x.x.x` address is your Ubuntu machine's local IP.

Test internet access:

```bash
ping google.com
```

---

## 2️⃣ Install OpenSSH Server

On Ubuntu:

```bash
sudo apt update
sudo apt install openssh-server
```

Enable SSH on boot:

```bash
sudo systemctl enable ssh
```

Start SSH now:

```bash
sudo systemctl start ssh
```

Check status:

```bash
sudo systemctl status ssh
```

You should see `active (running)`.

---

## 3️⃣ Connect from Another Machine

From your other device (Linux / WSL / macOS terminal):

```bash
ssh your_username@YOUR_UBUNTU_IP
```

Example:

```bash
ssh quack@xxx.xx.xxx.xxx
```

First connection will ask:

```
Are you sure you want to continue connecting?
```

Type:

```
yes
```

Enter your Ubuntu password.

You are now remotely controlling your Ubuntu server.

---

## 4️⃣ Deploy LANHub App

On Ubuntu:

Install Git if needed:

```bash
sudo apt install git
```

Clone your the working tree repository:

```bash
git clone https://github.com/theplatecrafter/Campus_Webpage
cd Campus_Webpage
```

Install Python + venv tools:

```bash
sudo apt install python3 python3-venv python3-pip
```

Create virtual environment:

```bash
python3 -m venv venv
```

Activate it:

```bash
source venv/bin/activate
```

Install dependencies:

```bash
pip install -r dependencies.txt
```

Test run:

```bash
python app.py
```

If using Flask-SocketIO production mode, ensure you are not using default Werkzeug without explicitly allowing it.

Stop test run with:

```
Ctrl+C
```

Make sure something like "Received <>, shutting down gracefully..." prints.

---

## 5️⃣ Create systemd Service

Create service file:

```bash
sudo nano /etc/systemd/system/lanhub.service
```

Paste:

```ini
[Unit]
Description=LANHub Server
After=network.target

[Service]
User=<Ubuntu_username>
WorkingDirectory=/home/<Ubuntu_username>/.../Campus_Webpage
ExecStart=/home/<Ubuntu_username>/.../Campus_Webpage/venv/bin/python app.py
Restart=always
RestartSec=5
Environment="PYTHONUNBUFFERED=1"
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```


Save and exit.

---

Reload systemd:

```bash
sudo systemctl daemon-reload
```

Enable auto-start on boot:

```bash
sudo systemctl enable lanhub
```

Start server:

```bash
sudo systemctl start lanhub
```

Check status:

```bash
sudo systemctl status lanhub
```

---



# Commands Overview (after setup)
---
## Disable All Sleep/Hibernation Actions
```bash
sudo systemctl mask sleep.target suspend.target hibernate.target hybrid-sleep.target
```

to undo:

```bash
sudo systemctl unmask sleep.target suspend.target hibernate.target hybrid-sleep.target
```
---
## Disable GUI (pour all CPU, network, and RAM to simple terminal)
This will allow the ubuntu desktop LTS to run on a terminal, instead of a full desktop. You can disable this anytime you want to get back to normal GUI mode.
Before doing this however, it is recommended to make sure the wifi is set to auto-reconnect

to enable terminal mode:
```bash
sudo systemctl set-default multi-user.target
```
reboot:
```bash
sudo reboot
```
the computer will boot to the Ubuntu terminal.

you can check what process Ubuntu is running by running:
```bash
top
```
or
```bash
htop
```

to disable terminal mode (in a ssh terminal or local terminal):
```bash
sudo systemctl set-default graphical.target
sudo reboot
```
---
## Connect to Server Terminal with Another Linux Terminal
Connect with:
```bash
ssh <Ubuntu_username>@<Ubuntu_ip>
```

Disconnect with:
```bash
exit
```
---

## To start/stop/reload/restart systemctl 
Reload systemd:
```bash
sudo systemctl daemon-reload
```
Enable auto-start on boot:
```bash
sudo systemctl enable lanhub
```
Start server:
```bash
sudo systemctl start lanhub
```
Stop server:
```bash
sudo systemctl stop lanhub
```
Check status:
```bash
sudo systemctl status lanhub
```


## View Live Logs

```bash
journalctl -u lanhub -f
```

This shows real-time server output.

---

## Updating Code Safely

When you update code:

```bash
sudo systemctl stop lanhub
```

Then:

```bash
git pull
```

Then restart:

```bash
sudo systemctl start lanhub
```


---





# Automatic Restart Behavior

Because we set:

```
Restart=always
```

systemd will restart the server if:

* Python crashes
* Unhandled exception exits program
* Process is killed

It will NOT restart if:

* You manually stop it (`systemctl stop`)

---

# Optional: Secure SSH (Recommended)

Generate SSH key on client machine:

```bash
ssh-keygen
```

Copy to Ubuntu:

```bash
ssh-copy-id your_username@YOUR_UBUNTU_IP
```

Then disable password login:

Edit:

```bash
sudo nano /etc/ssh/sshd_config
```

Set:

```
PasswordAuthentication no
```

Restart SSH:

```bash
sudo systemctl restart ssh
```

Now login uses SSH keys only.

---

# You Now Have

* Ubuntu running 24/7
* LAN SSH control
* Flask server auto-starting
* Auto-restart on crash
* Live logging via journalctl

Your laptop is now a proper Linux server.
