# Limit: one inventory, cluster chosen by the job's limit

One AAP inventory holds every cluster. Each cluster is a group named
`cluster_<name>`, and you pick the cluster at launch with the job's **limit**
(e.g. `cluster_cobalt`). The playbook refuses to run unless the limit selects
exactly one cluster.

```
inventory/clusters.json            # mock API response (replace with your real API)
inventory/dynamic_inventory.py     # inventory script; returns every cluster
playbook.yml                       # checks the limit, then runs against that cluster
aap/survey_spec.json               # survey: target_group
```

## How it works

```
inventory all-clusters
  └── source all-clusters-api: dynamic_inventory.py (no INV_CLUSTER)
        → 40 hosts in groups cluster_atlas … cluster_juniper, frontend, app, db

AAP API / UI launch
  limit: cluster_cobalt
        │
        ▼
inventory sync (Update on launch): every cluster; removed hosts deleted
        │
        ▼
playbook.yml
  1. limit set?                  no  → job fails
  2. hosts from one cluster?     no  → job fails
  3. runs on cobalt's hosts (optionally only frontend/app/db)
```

### Playbook behavior

| Launch with | Result |
|---|---|
| `limit: cluster_cobalt` | runs on all 4 cobalt hosts |
| `limit: cluster_cobalt`, `target_group: frontend` | runs on `cobalt-fe01`, `cobalt-fe02` only |
| `limit: cluster_cobalt:&frontend` | same as above, without the survey |
| `limit: cluster_nope` | job **fails**: `--limit leaves us with no hosts to target` |
| no limit | job **fails**: `No limit set. Launch with a limit such as cluster_cobalt, or this would run on every cluster.` |
| `limit: all` (or `cluster_a,cluster_b`) | job **fails**: `Limit 'all' selects 10 clusters (...). Use one, e.g. cluster_cobalt.` |

The two checks run once, before any other task, with `any_errors_fatal`, so
a bad limit stops the job before anything touches a host. They exist because
AAP can't make the limit field required. Without them, a launch that forgets
the limit runs on every host in every cluster.

An unknown cluster fails the job here, unlike the other two approaches. That
comes from `ansible-playbook` itself, before the playbook starts.

Cluster names with characters that aren't valid in group names are changed
to `_`, so `prod-east` is selected with `cluster_prod_east`.

## Connecting your real API

Edit `fetch_clusters()` in [inventory/dynamic_inventory.py](inventory/dynamic_inventory.py).
It must return:

```json
[{"name": "cobalt", "hosts": [{"hostname": "cobalt-fe01", "role": "frontend", "ip": "10.3.0.11"}]}]
```

This approach always loads every cluster, so each sync pulls the full list.
For real hosts, change `"ansible_connection": "local"` to
`"ansible_host": host["ip"]`.

## Run it locally

From this folder:

```bash
ansible-inventory -i inventory/dynamic_inventory.py --graph
ansible-playbook -i inventory/dynamic_inventory.py playbook.yml --limit cluster_cobalt
ansible-playbook -i inventory/dynamic_inventory.py playbook.yml --limit cluster_cobalt -e target_group=frontend
ansible-playbook -i inventory/dynamic_inventory.py playbook.yml              # fails: no limit
ansible-playbook -i inventory/dynamic_inventory.py playbook.yml --limit all  # fails: 10 clusters
```

## Set it up in AAP

### 1. Project
Create a Project named `aap-inventory` pointing to
`https://github.com/ryancbutler/aap-inventory.git`, branch `main`, and sync it.

### 2. Inventory
Create an inventory named `all-clusters`, then add a source named
`all-clusters-api`:

| Field | Value |
|---|---|
| Source | Sourced from a Project → `aap-inventory` |
| Inventory file | `limit/inventory/dynamic_inventory.py` |
| Source variables | none |
| Options | Overwrite, Overwrite variables, Update on launch (cache 300s) |

Sync it. It should contain 40 hosts and a `cluster_<name>` group for each
cluster. **Overwrite** deletes hosts the API no longer returns on each sync.

### 3. Job template
- Inventory: `all-clusters`
- Project: `aap-inventory`, Playbook: `limit/playbook.yml`
- Limit: leave empty, and turn on **Prompt on launch**
- Survey: add the question from [aap/survey_spec.json](aap/survey_spec.json)
  and turn the survey **on**

### 4. Launch from the AAP API

```bash
curl -k -u admin:PASSWORD -H "Content-Type: application/json" \
  -X POST https://AAP_HOST/api/controller/v2/job_templates/<ID>/launch/ \
  -d '{"limit": "cluster_cobalt", "extra_vars": {"target_group": "frontend"}}'
```

On AWX or AAP 2.4 and earlier, use `/api/v2/...` instead of `/api/controller/v2/...`.

> **Launch fields are silently dropped unless the template accepts them.**
> `limit` needs **Prompt on launch** on the Limit field, and `extra_vars`
> needs the survey turned on. If the launch response lists either one under
> `ignored_fields`, the template's default was used instead. A dropped limit
> is caught by the playbook's first check, so the job fails instead of
> running everywhere.
