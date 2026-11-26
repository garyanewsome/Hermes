# Querying the planner database

Two logins: `planner_reader` for everyday queries, `planner_writer` for
deliberate fixes. Nothing new is exposed on the network: connections go through
SSH to the homelab.

## One-time setup (on the homelab, from the Hermes folder)

Create the logins:

```bash
kubectl exec -i deploy/planner-postgres -- psql -U hermes -d planner -v ON_ERROR_STOP=1 < db/query-logins.sql
```

Set a different password for each (typed at a prompt, never stored in a file):

```bash
kubectl exec -it deploy/planner-postgres -- psql -U hermes -d planner -c '\password planner_reader'
```

```bash
kubectl exec -it deploy/planner-postgres -- psql -U hermes -d planner -c '\password planner_writer'
```

Find the database's cluster address (it stays the same unless the Service is
deleted and recreated):

```bash
kubectl get service planner-postgres -o jsonpath='{.spec.clusterIP}'
```

## Connecting from your computer (DBeaver)

Make one PostgreSQL connection per login.

| Setting | Value |
|---|---|
| Host | the cluster address from above |
| Port | `5432` |
| Database | `planner` |
| User | `planner_reader` or `planner_writer` |
| SSH tab | enable the tunnel: the host, user and key you already use to SSH to the homelab |

For the writer connection, set the connection type to **Production** and turn off
auto-commit, so changes wait for you to commit them.

Without DBeaver, open a tunnel and use any client against `localhost:5433`:

```bash
ssh -N -L 5433:<cluster address>:5432 <your homelab ssh name>
```

## Before changing data

- Look first: run the `WHERE` clause as a `SELECT`.
- `BEGIN;` then check the row count, then `COMMIT;` or `ROLLBACK;`.
- Backups run nightly and keep seven days.
- Spreadsheet workouts are overwritten when their date is imported again, so
  fix those in the sheet.
- Restoring a backup onto a fresh database: run `query-logins.sql` first, or
  the restore reports missing roles.
