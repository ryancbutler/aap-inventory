#!/usr/bin/env python3
"""
Ansible dynamic inventory script that can be filtered to one cluster.

Ansible calls this script with:
    --list          -> return all groups and hosts as JSON
    --host <name>   -> return vars for one host (we return {} because
                       all host vars are already in _meta.hostvars)

Input comes from an ENVIRONMENT VARIABLE:

    INV_CLUSTER     optional cluster name. If set, ONLY that cluster is
                    returned. If no cluster has that name, the inventory
                    is empty (no hosts, no groups).
                    If unset, every cluster is returned.

Data source: fetch_clusters() reads clusters.json next to this script, which
stands in for an API response. Replace that function with a real API call.

Groups produced:
    frontend, app, db       hosts by role
    cluster_<name>          all hosts in one cluster. Characters that are
                            not valid in group names become "_", so
                            "prod-east" -> "cluster_prod_east".
"""
import argparse
import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
ROLES = ["frontend", "app", "db"]


def fetch_clusters(cluster_name=None):
    """Return a list of clusters: [{"name": ..., "hosts": [{...}, ...]}].

    Real-world version, e.g. with requests:
        resp = requests.get(
            f"{API_URL}/clusters",
            params={"name": cluster_name} if cluster_name else None,
        )
        return resp.json()["clusters"]
    """
    with open(os.path.join(HERE, "clusters.json")) as f:
        clusters = json.load(f)["clusters"]
    if cluster_name:
        clusters = [c for c in clusters if c["name"] == cluster_name]
    return clusters


def group_name(cluster):
    return "cluster_" + re.sub(r"[^A-Za-z0-9_]", "_", cluster)


def build_inventory():
    # `or` handles variables that are set but empty (common with injectors).
    wanted = (os.environ.get("INV_CLUSTER") or "").strip() or None
    clusters = fetch_clusters(wanted)

    inventory = {"_meta": {"hostvars": {}}}
    if not clusters:
        # Unknown cluster: return an empty inventory.
        return inventory

    inventory["all"] = {"children": list(ROLES)}
    for role in ROLES:
        inventory[role] = {"hosts": []}

    for cluster in clusters:
        group = group_name(cluster["name"])
        inventory[group] = {"hosts": [], "vars": {"cluster_name": cluster["name"]}}
        inventory["all"]["children"].append(group)

        for host in cluster["hosts"]:
            name = host["hostname"]
            inventory[group]["hosts"].append(name)
            inventory[host["role"]]["hosts"].append(name)
            inventory["_meta"]["hostvars"][name] = {
                # Real hosts would use: "ansible_host": host["ip"]
                # local connection lets the demo run with no servers.
                "ansible_connection": "local",
                "host_ip": host["ip"],
                "role": host["role"],
                "cluster_name": cluster["name"],
            }

    return inventory


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--host")
    args = parser.parse_args()

    if args.host:
        print(json.dumps({}))
    else:
        print(json.dumps(build_inventory(), indent=2))


if __name__ == "__main__":
    main()
