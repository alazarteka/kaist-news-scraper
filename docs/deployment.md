# Deployment

This project is intended to run as a small unattended job on a machine you already reach over Tailscale.

## Recommended Layout

Use a split between config, state, and published output:

```text
/opt/herald/.venv/              package installation
/etc/herald/herald.toml         application config
/etc/herald/openrouter.env      optional API key
/var/lib/herald/                archive and cache state
/srv/herald/site/               rendered static site
```

Suggested config values for that layout are in `deploy/herald.toml.production.example`.

## Install

Create an isolated virtual environment and install the package:

```bash
python3 -m venv /opt/herald/.venv
/opt/herald/.venv/bin/pip install git+https://github.com/alazarteka/kaist-news-scraper.git
```

Then create a config file:

```bash
/opt/herald/.venv/bin/herald init-config --output /etc/herald/herald.toml
```

Adjust the paths in `/etc/herald/herald.toml` to match the target machine.

## OpenRouter Key

If you want model-backed classification and title translation, store the key in an environment file:

```bash
OPENROUTER_API_KEY=your-key-here
```

The included systemd service reads `/etc/herald/openrouter.env` if it exists. If you prefer rules-only operation, omit the file.

## Scheduling

Two unattended-run examples are included:

- `deploy/systemd/herald.service`
- `deploy/systemd/herald.timer`
- `deploy/cron/herald.cron`

Use one scheduling mechanism, not both.

## Serving The Site

Herald only renders static files. Serve the configured `site_dir` with whatever private web server already fits your machine:

- nginx
- caddy
- a simple local static file server behind Tailscale

No application server is required.
