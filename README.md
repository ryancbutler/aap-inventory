# AAP dynamic inventory: run a job against one cluster

Four ways to run an AAP job against **one cluster chosen at launch**,
including launches from the AAP API. All four use the same mock data. The
first three read it with an inventory script, and `constructed/` reads it with
an inventory plugin:

- 10 clusters: `atlas`, `boreal`, `cobalt`, `delta`, `ember`, `falcon`,
  `granite`, `harbor`, `ion`, `juniper`
- Each cluster has 2 frontends, 1 app server, and 1 database server
- An optional `target_group` (`all`, `frontend`, `app`, `db`) narrows the run
  to one role inside the cluster

Each folder is self-contained, with setup steps, required credentials, a
scaling diagram, and pros and cons in its README.

| | [runtime/](runtime/) | [inventory-level/](inventory-level/) | [limit/](limit/) | [constructed/](constructed/) |
|---|---|---|---|---|
| How it works | The playbook queries the API for the cluster and adds the hosts with `add_host` | One AAP inventory per cluster, synced from the API | One AAP inventory with every cluster; the job's limit picks one | One AAP inventory with every cluster, plus one constructed inventory per cluster that filters it |
| Select cluster with | `extra_vars: {cluster_name: cobalt}` | `inventory: <id of cluster-cobalt>` | `limit: cluster_cobalt` | `inventory: <id of constructed-cobalt>` |
| AAP objects as clusters grow | stays at 1 template + 1 empty inventory | 1 inventory + 1 source per cluster | stays at 1 template + 1 inventory | 1 constructed inventory per cluster, plus 1 source inventory |
| API calls per sync | 1 per job, for one cluster | 1 per cluster | 1 for all clusters | 1 for all clusters |
| Hosts stored in AAP | no, only for the job | yes, one inventory per cluster | yes, all clusters in one inventory | yes, all together and per cluster |
| Per-cluster access control | no | yes, through **Use** on each inventory | no | yes, through **Use** on each constructed inventory |
| Removed host | not returned on the next run | deleted on the next sync | deleted on the next sync | deleted on the next scheduled sync |
| New cluster | works right away | rerun the setup playbook | works after the next sync | rerun the setup playbook |
| Unknown cluster | job succeeds with no hosts | no inventory to select, so nothing launches | job fails: limit matches no hosts | no inventory to select, so nothing launches |
| Forgot to pick a cluster | job fails: `Set cluster_name` | runs on the template's default inventory | job fails: playbook requires a limit | runs on the template's default inventory |
| Cluster API down | job fails | sync fails or, with a script that hides errors, empties the inventory | sync fails or, with a script that hides errors, empties the inventory | sync fails and the last good hosts are kept |
| Extra AAP credential | none | AAP credential for the setup playbook | none | AAP credential for the setup playbook |
| Needs | any AAP or AWX | any AAP or AWX | any AAP or AWX | AAP 2.4+ or AWX 22+ |

**Which to pick**
- **runtime/** if you want the fewest AAP objects and always-current data,
  and don't need to browse hosts in AAP.
- **inventory-level/** if different teams own different clusters and must
  only be able to run against their own.
- **limit/** if you want hosts browsable in AAP without one inventory per
  cluster, and the total host count is small enough to sync in one go.
- **constructed/** if you want per-cluster access control like
  inventory-level/ but only one API sync for all clusters, and data up to one
  sync interval old (15 minutes by default) is acceptable.

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

### constructed/

```json
GET  /api/controller/v2/inventories/?name=constructed-cobalt    → id 14
POST /api/controller/v2/job_templates/<constructed-cluster>/launch/
{"inventory": 14, "extra_vars": {"target_group": "frontend"}}
```

1. Separately from any job, a schedule syncs `clusters-source` from the API
   every 15 minutes. The `cluster_api` plugin loads every cluster, each as a
   `cluster_<name>` group. If the API call fails, the sync fails and the
   hosts from the last good sync stay.
2. The caller looks up the ID of constructed inventory `constructed-cobalt`.
   If the lookup returns `"count": 0`, there's no such cluster and nothing is
   launched.
3. AAP checks that the caller has **Use** on `constructed-cobalt`, then
   starts the job.
4. Because the constructed source has **Update on launch** with no cache,
   AAP first rebuilds `constructed-cobalt` from the hosts `clusters-source`
   holds in its database, keeping only `cluster_cobalt`. This doesn't call
   the API.
5. The playbook runs against the inventory. With `hosts: frontend`, that's
   `cobalt-fe01` and `cobalt-fe02`.

## Why the inventory sync can't take a launch value

AAP syncs inventory as a separate job before the playbook runs, and that job
sees only the inventory source's own settings. A survey answer or API
`extra_vars` value never reaches it. That's why `runtime/` runs the script
from inside the playbook, `inventory-level/` sets the cluster in each
inventory source ahead of time, `limit/` loads every cluster and narrows
the job with the limit instead, and `constructed/` loads every cluster and
sets a fixed limit on each constructed inventory ahead of time.

## Subscription host counts

AAP counts every unique host a job automates toward your subscription, with
every approach (including hosts added with `add_host`). When a host is
retired for good, delete it under **Analytics → Host Metrics** so it stops
counting.
