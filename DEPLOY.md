# Deploying the dashboard to Streamlit Community Cloud

The app shows a named client's plan. Keep the repository **private** and the app restricted to
**specific viewers**. Do every step below yourself; nothing in this project pushes or deploys.

## 0. Gate: must pass before every push

```bash
.venv/bin/python -m pytest -q                 # all tests pass
.venv/bin/python run_hardening.py             # A2 vs A4 seed check (the "why A2" line reads it)
.venv/bin/python run_simulation.py --final    # official 500,000-path outputs, end_result.md
.venv/bin/python run_ips.py                   # IPS charts in outputs/ips/
.venv/bin/python check_deploy.py              # must print "Ready to deploy." and exit 0
```

`check_deploy.py` fails while any of these is true:
- an assumption still has `status: placeholder` (source: TODO)
- a `ladder.csv` row's data_status contains "ESTIMATE"
- `outputs/` was generated from a different `config.yaml` or `ladder.csv` than the current ones

If `ladder.csv` ever changes, rebuild it from the fills first: `.venv/bin/python build_ladder.py`.

## 1. Put the project on GitHub (private)

The folder is not a git repository yet. `.gitignore` already excludes `.venv/` and caches.
Commit `outputs/` too: it holds the official numbers, `end_result.md` and the IPS charts.

```bash
git init -b main
git add .
git status            # check: no .venv/, nothing you don't want shared
git commit -m "Monte Carlo plan model and dashboard"
```

On github.com: **New repository** → name it → choose **Private** → do *not* add a README,
.gitignore or license (the repo must start empty) → **Create repository**. GitHub then shows the
two commands to connect and push; they look like:

```bash
git remote add origin https://github.com/<you>/<repo>.git
git push -u origin main
```

Files the app needs at runtime: `app.py`, `config.yaml`, `ladder.csv`, `mcsim/`,
`requirements.txt`, `.streamlit/config.toml` (the dark theme). It reads nothing outside the
repository and does not need `outputs/`.

## 2. Create the app

1. Go to https://share.streamlit.io and sign in with the GitHub account that owns the repo (the
   first time, authorise Streamlit to read your private repositories when GitHub asks).
2. Click **Create app** (upper right) → **"Yup, I have an app."**
3. Repository: your private repo. Branch: `main`. Main file path: `app.py`. Optionally set a
   short **App URL**.
4. Open **Advanced settings** → **Python version**: pick **3.14** if it is offered, otherwise the
   newest offered (3.12 or newer is required by the pinned numpy and pandas). Tested locally on
   Python 3.14. No secrets are needed. Set the version now: the deploy page only documents choosing
   it here, before the first deploy.
5. Click **Deploy** / **Save**. The first build installs `requirements.txt` and takes a few minutes.

Screen labels on share.streamlit.io change from time to time; the settings above are the ones that
matter.

## 3. Restrict who can see it

An app deployed from a private repo starts private: only developers in your workspace can see it.

- To add viewers: open the app → **Share** (upper right) → enter an email → **Invite**. Or app
  **Settings** → **Sharing** → add or remove viewers → **Save**.
- Keep "Who can view this app" set to **Only specific people can view this app**. Do not click
  **Make this app public**.
- Viewers sign in to see it (Google sign-in if their email is a Google account, otherwise a one-time
  email link).
- Viewers you add **can invite other viewers** and see the app's analytics. Invite only people you
  trust with the client's data.
- Community Cloud allows **one private app at a time** from private repositories. To deploy a
  second one you would have to make the first public or delete it.

## 4. Check the deployed app

- Status bar along the bottom: "Official inputs", "Ladder: all quoted", "Assumptions: 0
  placeholders", "Deploy ready".
- The first two quotes in the top strip are "Facility contribution 2033, median" and "Example
  co-sponsor range (method)". The dashboard runs 10,000 paths, so its figures differ slightly from
  the official 500,000-path numbers in `outputs/headline.md` and `outputs/end_result.md`.
- Change an input (e.g. US ret %) and the summary line turns to "Modified inputs"; click
  **Official** in the toolbar and it goes back.

## 5. Updating

Push to `main`; Community Cloud redeploys automatically. The app's caches are keyed on a hash of
`config.yaml` and `ladder.csv`, so new inputs are picked up without a restart. Rerun section 0
before every push that changes inputs.
