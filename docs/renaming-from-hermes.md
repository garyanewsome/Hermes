# Moving from Hermes to Naradi

A one-time cutover. Do the steps in order; the app is down for a few minutes
during step 4.

## 1. Rename the repository and merge

Done from your computer: rename the GitHub repository to `Naradi`, merge the
rename into `main` here and in vault-keeper, and push.

## 2. Move the vault folder

In the Obsidian vault: rename `01 Hermes` to `01 Naradi`, and change the
`## 🤖 Hermes` heading in the Daily Note template to `## 🤖 Naradi`.
Older notes keep their heading; vault-keeper still finds it.

## 3. On the homelab

Update vault-keeper first:

```bash
cd ~/vault-keeper && ./deploy.sh
```

Then rename the folder:

```bash
mv ~/Hermes ~/Naradi
```

```bash
git -C ~/Naradi remote set-url origin https://github.com/garyanewsome/Naradi.git
```

## 4. Migrate

```bash
cd ~/Naradi && git pull && scripts/migrate-from-hermes.sh
```

It checks everything before changing anything and asks you to type `migrate`.
It backs up the database and data, copies the data to
`/mnt/storage/naradi-data`, renames the database user, and starts Naradi on the
same port. Later updates are `./deploy.sh` as before.

If something is wrong:

```bash
cd ~/Naradi && scripts/migrate-from-hermes.sh --rollback
```

Rolling back keeps the database as it is; chats made after the migration stay
in the renamed data folder and don't come back with it.

## 5. Your devices

- Sign in again (the login cookie has a new name).
- Remove the old home-screen shortcut and add Naradi again.
- If you use the `.home.local` name, change it to `naradi.home.local` in
  `/etc/hosts`. The `:30080` address and Tailscale work as before.
- In DBeaver, nothing changes: `planner_reader` and `planner_writer` keep
  their names.
- Optional host helpers pick up their new descriptions when you next copy them
  over (`statusd`, `searxng`); they work without it.

## 6. Clean up, after a few good days

```bash
kubectl delete pvc hermes-data && kubectl delete pv hermes-data-pv
```

```bash
kubectl delete secret hermes-auth-secret
```

```bash
kubectl patch secret planner-postgres-secret --type json -p '[{"op":"remove","path":"/data/hermes-db-url"}]'
```

```bash
sudo k3s ctr images rm docker.io/library/hermes:latest && docker image rm hermes:latest
```

Then delete `/mnt/storage/hermes-data` and the
`/mnt/storage/naradi-migration-*` backup once you are sure you don't need them.
