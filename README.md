
<p align="center">

<img src="web/static/logo.png" width="220">

</p>

**Eagle** is an open-source application for generating and sending personalized job applications using AI.

It generates tailored CVs, cover letters, and emails from your existing profile and company contacts. Applications can be reviewed as drafts or sent directly through SMTP.

## Features

- AI-generated CVs, cover letters, and emails with you custom LaTeX templates

- CSV-based company contacts

- Draft management and application history

- Multi-user accounts and file management

- Web interface with light and dark modes

- provider-agnostic API and SMTP configuration

- CLI support

## Installation

### Requirements

- Python 3.12+

- LaTeX (`pdflatex`)

- SQLite

- SMTP account

- OpenAI-compatible API

On Debian/Ubuntu:

```bash
sudo apt update
sudo apt install python3 python3-venv texlive-latex-base texlive-latex-recommended texlive-latex-extra
```

Clone the repository and create a virtual environment:

```bash
git clone https://github.com/JulienLargetPiet/Eagle.git
cd Eagle

python3 -m venv menv
source menv/bin/activate

pip install -r requirements.txt
```

Create a `.env` file:

```env
EAGLE_SESSION_SECRET=replace-with-a-long-random-secret
```

Generate a secret with:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(48))"
```

In the `.env` file, you also have those variables to configure:

```

AI_API_KEY=...
AI_MODEL=examplerouter/free

SENDER_EMAIL=example@test.com
SMTP_HOST=smtp.example.com
SMTP_PORT=465
SMTP_USER=example@test.com
SMTP_PASSWORD=...

```

## Running the Web Application

```bash
uvicorn web.server:app --host 127.0.0.1 --port 9001 --env-file .env
```

Visit `http://127.0.0.1:9001` and create an account.

Each user has an isolated workspace under `users/<username>/`, containing contacts, templates, drafts, and applications.

## Self-Hosting

First, in `/etc/nginx/nginx.conf`, add this limit conf variable in the `http` block:

```

limit_req_zone $binary_remote_addr zone=eagle_limit:10m rate=10r/m;

```

Then yu can create the Nginx conf file at `/etc/nginx/sites-available/eagle.conf`:


```nginx

# HTTP -> HTTPS
server {
    listen 80;
    listen [::]:80;

    server_name URL;

    return 301 https://$host$request_uri;
}



server {
    listen 443 ssl;
    listen [::]:443 ssl;

    server_name URL;

    ssl_certificate /etc/letsencrypt/live/HOSTNAME/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/HOSTNAME/privkey.pem;

    client_max_body_size 6M;

    # Rate limit login and registration
    location = /login {
        limit_req zone=eagle_limit burst=5 nodelay;
        limit_req_status 429;

        proxy_pass http://127.0.0.1:9001;
        include /etc/nginx/proxy_params;
    }

    location = /register {
        limit_req zone=eagle_limit burst=5 nodelay;
        limit_req_status 429;

        proxy_pass http://127.0.0.1:9001;
        include /etc/nginx/proxy_params;
    }

    location / {
        proxy_pass http://127.0.0.1:9001;

        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        proxy_read_timeout 300s;
    }
}


```

In the above conf, modify `URL` with yours and also `HOSTNAME`.

Verify the synthax:

```bash

sudo nginx -t

```

Now, make the chosen URL point to your ip addr (usually via your vps provider).

Now, obtain the certificates (`fullchain.pem` and `private.pem`):

```bash

sudo certbot certonly --standalone -d eagle.julienlargetpiet.tech

```

Create a dedicated system user and give it the necessary permissions:

```bash
sudo useradd --system --user-group --shell /usr/sbin/nologin eagle
sudo chown -R eagle:eagle /var/www/Eagle
```

Create `/etc/systemd/system/eagle.service`:

```ini
[Unit]
Description=Eagle Web Application
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=eagle
Group=eagle
WorkingDirectory=/var/www/Eagle
EnvironmentFile=/var/www/Eagle/.env
ExecStart=/var/www/Eagle/menv/bin/python -m uvicorn web.server:app --host 127.0.0.1 --port 9001
Restart=on-failure
RestartSec=5
UMask=0077
NoNewPrivileges=true

[Install]
WantedBy=multi-user.target
```

Enable and start Eagle:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now eagle
```

Check its status and logs:

```bash
sudo systemctl status eagle
sudo journalctl -u eagle -f
```

Now, reload `Nginx`:

```bash

sudo systemctl reload nginx

```






