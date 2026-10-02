# AAP dynamic inventory: run a job against one cluster

Three ways to run an AAP job against **one cluster chosen at launch**,
including launches from the AAP API. All three use the same inventory script
and mock data:

- 10 clusters: `atlas`, `boreal`, `cobalt`, `delta`, `ember`, `falcon`,
  `granite`, `harbor`, `ion`, `juniper`
- Each cluster has 2 frontends, 1 app server, and 1 database server
- An optional `target_group` (`all`, `frontend`, `app`, `db`) narrows the run
  to one role inside the cluster

Each folder is self-contained, with setup steps, required credentials, a
scaling diagram, and pros and cons in its README.

| | [runtime/](runtime/) | [inventory-level/](inventory-level/) | [limit/](limit/) |
|---|---|---|---|
| How it works | The playbook queries the API for the cluster and adds the hosts with `add_host` | One AAP inventory per cluster, synced from the API | One AAP inventory with every cluster; the job's limit picks one |
| Select cluster with | `extra_vars: {cluster_name: cobalt}` | `inventory: <id of cluster-cobalt>` | `limit: cluster_cobalt` |
| AAP objects as clusters grow | stays at 1 template + 1 empty inventory | 1 inventory + 1 source per cluster | stays at 1 template + 1 inventory |
| Hosts stored in AAP | no, only for the job | yes, one inventory per cluster | yes, all clusters in one inventory |
| Per-cluster access control | no | yes, through **Use** on each inventory | no |
| Removed host | not returned on the next run | deleted on the next sync | deleted on the next sync |
| New cluster | works right away | rerun the setup playbook | works after the next sync |
| Unknown cluster | job succeeds with no hosts | no inventory to select, so nothing launches | job fails: limit matches no hosts |
| Forgot to pick a cluster | job fails: `Set cluster_name` | runs on the template's default inventory | job fails: playbook requires a limit |
| Extra AAP credential | none | AAP credential for the setup playbook | none |

**Which to pick**
- **runtime/** if you want the fewest AAP objects and always-current data,
  and don't need to browse hosts in AAP.
- **inventory-level/** if different teams own different clusters and must
  only be able to run against their own.
- **limit/** if you want hosts browsable in AAP without one inventory per
  cluster, and the total host count is small enough to sync in one go.

## How a job runs for one cluster

Each walk-through below follows one launch against `cobalt`, restricted to
its frontends.

### runtime/

```json
POST /api/controller/v2/job_templates/<runtime-cluster>/launch/
{"extra_vars": {"cluster_name": "cobalt", "target_group": "frontend"}}
```

1. AAP checks the answers against the survey and starts a job with the empty
   `runtime-hosts` inventory.
2. **Play 1** runs on `localhost` inside the execution environment and
   checks that `cluster_name` is set. If it isn't, the job fails here.
3. Play 1 runs `dynamic_inventory.py --list` with `INV_CLUSTER=cobalt`. The
   script asks the cluster API for cobalt only.
4. The script returns cobalt's 4 hosts. If cobalt doesn't exist, it returns
   nothing, the job reports `Cluster cobalt not found` and succeeds without
   doing anything.
5. `add_host` adds `cobalt-fe01`, `cobalt-fe02`, `cobalt-app01` and
   `cobalt-db01` to the job's in-memory inventory, in groups
   `target_cluster` and `frontend`, `app` or `db`.
6. **Play 2** targets `target_cluster:&frontend` and runs on `cobalt-fe01`
   and `cobalt-fe02`.
7. The job ends and the added hosts are gone. The next launch asks the API
   again.

### inventory-level/

```json
GET  /api/controller/v2/inventories/?name=cluster-cobalt    → id 6
POST /api/controller/v2/job_templates/<inventory-level-cluster>/launch/
{"inventory": 6, "extra_vars": {"target_group": "frontend"}}
```

1. The caller looks up the ID of inventory `cluster-cobalt`. If the lookup
   returns `"count": 0`, there's no such cluster and nothing is launched.
2. AAP checks that the caller has **Use** on `cluster-cobalt`, then starts the
   job.
3. Because the source has **Update on launch**, AAP first syncs
   `cluster-cobalt`, unless it synced in the last 300 seconds. The sync runs
   the script with `INV_CLUSTER=cobalt` from the source's variables.
   **Overwrite** deletes any host the API no longer returns.
4. The playbook runs against the inventory. With `hosts: frontend`, that's
   `cobalt-fe01` and `cobalt-fe02`.
5. The hosts stay in `cluster-cobalt`, where they can be browsed along with
   their job history.

### limit/

```json
POST /api/controller/v2/job_templates/<limit-cluster>/launch/
{"limit": "cluster_cobalt", "extra_vars": {"target_group": "frontend"}}
```

1. AAP starts a job against the `all-clusters` inventory with
   `--limit cluster_cobalt`.
2. Because the source has **Update on launch**, AAP first syncs
   `all-clusters`, unless it synced in the last 300 seconds. The sync loads
   every cluster, each as a `cluster_<name>` group.
3. `ansible-playbook` applies the limit. If it matches no hosts (an unknown
   cluster), the job fails here.
4. The play targets `frontend`, narrowed by the limit to `cobalt-fe01` and
   `cobalt-fe02`.
5. The guard tasks run once: a limit must be set, and every targeted host
   must belong to one cluster. If either check fails, the job stops before
   any host runs any work.
6. The remaining tasks run on `cobalt-fe01` and `cobalt-fe02`.

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
