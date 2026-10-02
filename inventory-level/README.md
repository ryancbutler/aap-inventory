# Inventory level: one AAP inventory per cluster

Each cluster gets its own AAP inventory. That inventory's source runs the
script with `INV_CLUSTER` set in **Source variables**, so it only ever
contains that cluster's hosts. You pick the cluster by picking the inventory
at launch.

```
inventory/clusters.json            # mock API response (replace with your real API)
inventory/dynamic_inventory.py     # inventory script; INV_CLUSTER filters to one cluster
playbook.yml                       # runs against whatever the selected inventory holds
aap/setup_cluster_inventories.yml  # creates and syncs one AAP inventory per cluster
aap/survey_spec.json               # survey: target_group
```

## How it works

```
aap/setup_cluster_inventories.yml (run once, then when clusters are added)
  for each cluster the API returns:
    inventory cluster-<name>
      └── source <name>-api: dynamic_inventory.py, INV_CLUSTER=<name>

AAP API / UI launch
  inventory: <id of cluster-cobalt>
        │
        ▼
inventory sync (Update on launch): only cobalt hosts; removed hosts deleted
        │
        ▼
playbook.yml → runs on those hosts (optionally only frontend/app/db)
```

### Inventory script behavior

| `INV_CLUSTER` | Returned |
|---|---|
| unset | all 10 clusters (40 hosts), used by the setup playbook to list clusters |
| `cobalt` | only `cobalt-fe01`, `cobalt-fe02`, `cobalt-app01`, `cobalt-db01` |
| `nope` | empty inventory: `{"_meta": {"hostvars": {}}}` |

## What one cluster inventory looks like

Inventory `cluster-cobalt` → Source `cobalt-api`:

| Field | Value |
|---|---|
| Source | Sourced from a Project → `aap-inventory` |
| Inventory file | `inventory-level/inventory/dynamic_inventory.py` |
| Source variables | `INV_CLUSTER: cobalt` |
| Options | Overwrite, Overwrite variables, Update on launch (cache 300s) |

After a sync it contains only that cluster's hosts:

```
$ INV_CLUSTER=cobalt ansible-inventory -i inventory/dynamic_inventory.py --graph
@all:
  |--@ungrouped:
  |--@frontend:
  |  |--cobalt-fe01
  |  |--cobalt-fe02
  |--@app:
  |  |--cobalt-app01
  |--@db:
  |  |--cobalt-db01
  |--@cluster_cobalt:
  |  |--cobalt-fe01
  |  |--cobalt-fe02
  |  |--cobalt-app01
  |  |--cobalt-db01
```

Each host gets variables like `cluster_name: cobalt`, `role: frontend`,
`host_ip: 10.3.0.11`.

**Overwrite** is what keeps this clean long term: on each sync, hosts and
groups the API no longer returns are deleted from the inventory.

## Connecting your real API

Edit `fetch_clusters()` in [inventory/dynamic_inventory.py](inventory/dynamic_inventory.py).
It must return:

```json
[{"name": "cobalt", "hosts": [{"hostname": "cobalt-fe01", "role": "frontend", "ip": "10.3.0.11"}]}]
```

Filter on the API side if it supports it. The docstring has a `requests`
example. For real hosts, change
`"ansible_connection": "local"` to `"ansible_host": host["ip"]`.

## Run it locally

From this folder:

```bash
INV_CLUSTER=cobalt ansible-inventory -i inventory/dynamic_inventory.py --graph
INV_CLUSTER=cobalt ansible-playbook -i inventory/dynamic_inventory.py playbook.yml -e target_group=frontend
INV_CLUSTER=nope   ansible-playbook -i inventory/dynamic_inventory.py playbook.yml   # no hosts matched
```

## Set it up in AAP

### 1. Project
Create a Project named `aap-inventory` pointing to
`https://github.com/ryancbutler/aap-inventory.git`, branch `main`, and sync it.

### 2. Create the cluster inventories
Create a job template for
[aap/setup_cluster_inventories.yml](aap/setup_cluster_inventories.yml):
- Inventory: any (the play runs on localhost)
- Project: `aap-inventory`, Playbook: `inventory-level/aap/setup_cluster_inventories.yml`
- Credentials: a **Red Hat Ansible Automation Platform** credential (so it can
  call the AAP API)
- Execution environment: one that includes `ansible.controller`, e.g.
  `ee-supported-rhel9`. On AWX, the default AWX EE works (it has `awx.awx`).

Launch it. It asks the script for every cluster, then creates
`cluster-<name>` and its source for each one and syncs it. Change the `vars:`
at the top if your organization or project names differ.

Rerun it when clusters are added. It doesn't delete inventories for clusters
that were removed. Delete those by hand, or their sync will return no hosts.

To create one by hand instead, follow the table in
[What one cluster inventory looks like](#what-one-cluster-inventory-looks-like).

### 3. Job template
- Inventory: any `cluster-*` inventory, with **Prompt on launch** turned on
- Project: `aap-inventory`, Playbook: `inventory-level/playbook.yml`
- Survey: add the question from [aap/survey_spec.json](aap/survey_spec.json)
  and turn the survey **on**

### 4. Launch from the AAP API

```bash
# Find the inventory ID. "count": 0 means no such cluster.
curl -k -u admin:PASSWORD \
  "https://AAP_HOST/api/controller/v2/inventories/?name=cluster-cobalt"

curl -k -u admin:PASSWORD -H "Content-Type: application/json" \
  -X POST https://AAP_HOST/api/controller/v2/job_templates/<ID>/launch/ \
  -d '{"inventory": <INVENTORY_ID>, "extra_vars": {"target_group": "frontend"}}'
```

On AWX or AAP 2.4 and earlier, use `/api/v2/...` instead of `/api/controller/v2/...`.

> **Launch fields are silently dropped unless the template accepts them.**
> `inventory` needs **Prompt on launch** on the Inventory field, and
> `extra_vars` needs the survey turned on. If the launch response lists either
> one under `ignored_fields`, the template's default was used instead.

If the inventory ends up empty, for example because the cluster was removed
from the API, the play reports `no hosts matched` and the job succeeds
without doing anything.
