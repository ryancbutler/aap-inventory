# AAP dynamic inventory: run a job against one cluster

Three ways to run an AAP job against **one cluster chosen at launch**,
including launches from the AAP API.

- 10 clusters: `atlas`, `boreal`, `cobalt`, `delta`, `ember`, `falcon`,
  `granite`, `harbor`, `ion`, `juniper`
- Each cluster has 2 frontends, 1 app server, and 1 database server
- If the cluster doesn't exist, nothing runs on any host

| | [runtime/](runtime/) | [inventory-level/](inventory-level/) | [limit/](limit/) |
|---|---|---|---|
| How it works | The playbook queries the API for the cluster and adds the hosts with `add_host` | One AAP inventory per cluster, synced from the API | One AAP inventory with every cluster; the job's limit picks one |
| Select cluster with | `extra_vars: {cluster_name: cobalt}` | `inventory: <id of cluster-cobalt>` | `limit: cluster_cobalt` |
| Hosts stored in AAP | no, only for the job | yes, browsable in the UI | yes, all clusters in one inventory |
| Removed host | not returned on the next run | deleted on the next sync (**Overwrite** on) | deleted on the next sync (**Overwrite** on) |
| New cluster | works right away | rerun the setup playbook | works after the next sync |
| Unknown cluster | job succeeds with no hosts | no inventory to select, so nothing launches | job fails: limit matches no hosts |
| Forgot to pick a cluster | job fails: `Set cluster_name` | runs on the template's default inventory | job fails: playbook requires a limit |

Each folder is self-contained, with its own copy of the inventory script
and mock API data. Start with the README in the folder you
want to use.

## Why the inventory sync can't take a launch value

AAP syncs inventory as a separate job before the playbook runs, and that job
sees only the inventory source's own settings. A survey answer or API
`extra_vars` value never reaches it. That's why `runtime/` runs the script
from inside the playbook, `inventory-level/` sets the cluster in each
inventory source ahead of time, and `limit/` loads every cluster and narrows
the job with the limit instead.

## Subscription host counts
AAP counts every unique host a job automates toward your subscription, with
every approach (including hosts added with `add_host`). When a host is
retired for good, delete it under **Analytics → Host Metrics** so it stops
counting.
