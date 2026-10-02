# Runtime: load one cluster during the job

The cluster name is passed at launch. The playbook asks the API for that
cluster and adds its hosts to the job in memory. Nothing is stored in an AAP
inventory, so there's nothing to clean up when hosts are removed.

```
inventory/clusters.json            # mock API response (replace with your real API)
inventory/dynamic_inventory.py     # inventory script; INV_CLUSTER filters to one cluster
playbook.yml                       # loads the requested cluster, then runs against it
aap/survey_spec.json               # survey: cluster_name, target_group
```

## How it works

```
AAP API / UI launch
  extra_vars: {cluster_name: cobalt}
        │
        ▼
playbook.yml, play 1 (localhost, inside the execution environment)
  runs: INV_CLUSTER=cobalt dynamic_inventory.py --list
        │   script asks the API for cluster "cobalt" only
        ▼
  add_host → cobalt-fe01, cobalt-fe02, cobalt-app01, cobalt-db01
        │
        ▼
playbook.yml, play 2 → runs on those hosts (optionally only frontend/app/db)
```

### Inventory script behavior

| `INV_CLUSTER` | Returned |
|---|---|
| unset | all 10 clusters (40 hosts), handy for local testing |
| `cobalt` | only `cobalt-fe01`, `cobalt-fe02`, `cobalt-app01`, `cobalt-db01` |
| `nope` | empty inventory: `{"_meta": {"hostvars": {}}}` |

Groups: `frontend`, `app`, `db`, and `cluster_<name>` (e.g. `cluster_cobalt`).

### Playbook behavior

| Launch with | Result |
|---|---|
| `cluster_name=cobalt` | runs on all 4 cobalt hosts |
| `cluster_name=cobalt`, `target_group=frontend` | runs on `cobalt-fe01`, `cobalt-fe02` only |
| `cluster_name=nope` | prints `Cluster nope not found. Nothing to do.`, job **succeeds** with no hosts |
| no `cluster_name` | job fails: `Set cluster_name` |

To make an unknown cluster **fail** the job instead, add this after the
"Parse the result" task:

```yaml
    - name: Fail if the cluster was not found
      ansible.builtin.assert:
        that: cluster_hosts | length > 0
        fail_msg: "Cluster {{ cluster_name }} not found."
```

## Connecting your real API

Edit `fetch_clusters()` in [inventory/dynamic_inventory.py](inventory/dynamic_inventory.py).
It must return:

```json
[{"name": "cobalt", "hosts": [{"hostname": "cobalt-fe01", "role": "frontend", "ip": "10.3.0.11"}]}]
```

Filter on the API side if it supports it, so only one cluster comes back. The
docstring has a `requests` example. For real hosts, change `"ansible_connection": "local"` to `"ansible_host": host["ip"]` in the
script and in the `add_host` task.

## Run it locally

From this folder:

```bash
./inventory/dynamic_inventory.py --list                      # all clusters
INV_CLUSTER=cobalt ./inventory/dynamic_inventory.py --list   # one cluster
INV_CLUSTER=nope ./inventory/dynamic_inventory.py --list     # empty

ansible-playbook playbook.yml -e cluster_name=cobalt
ansible-playbook playbook.yml -e cluster_name=cobalt -e target_group=frontend
ansible-playbook playbook.yml -e cluster_name=nope
```

## Set it up in AAP

### 1. Project
Create a Project pointing to
`https://github.com/ryancbutler/aap-inventory.git`, branch `main`, and sync it.

### 2. Inventory (empty placeholder)
A job template must have an inventory, but this playbook loads hosts itself
on every run. Create an inventory named `runtime-hosts` with **no hosts and
no sources**. The first play runs on the implicit localhost, which needs no
inventory entry.

Nothing is ever written to this inventory. Hosts added with `add_host` exist
only for that job, so a host removed from your API simply stops appearing in
later runs.

### 3. Job template
- Inventory: `runtime-hosts`
- Project: the project, Playbook: `runtime/playbook.yml`
- Survey: add the questions from [aap/survey_spec.json](aap/survey_spec.json)
  and turn the survey **on**

Load the survey with the API instead of the UI (from the repo root):
```bash
curl -k -u admin:PASSWORD -H "Content-Type: application/json" \
  -X POST https://AAP_HOST/api/controller/v2/job_templates/<ID>/survey_spec/ \
  -d @runtime/aap/survey_spec.json
```

### 4. Launch from the AAP API

```bash
curl -k -u admin:PASSWORD -H "Content-Type: application/json" \
  -X POST https://AAP_HOST/api/controller/v2/job_templates/<ID>/launch/ \
  -d '{"extra_vars": {"cluster_name": "cobalt", "target_group": "frontend"}}'
```

On AWX or AAP 2.4 and earlier, use `/api/v2/...` instead of `/api/controller/v2/...`.

> **extra_vars are silently dropped unless the template accepts them.**
> Turn on the survey (survey variables are accepted) or turn on **Prompt on
> launch** for Variables. Check the launch response: if `ignored_fields`
> contains `extra_vars`, the value never reached the playbook.

## Precedence
Extra vars beat everything else. If the job template, survey, and launch
request all set a variable, the launch-time value wins.
