"""Inventory plugin that loads every cluster from the cluster API."""
from __future__ import annotations

DOCUMENTATION = r"""
name: cluster_api
short_description: Load clusters and their hosts from the cluster API
description:
  - Returns every cluster. Each cluster becomes a group named
    C(cluster_<name>), and each host is also put in a group named after its
    role (C(frontend), C(app), C(db)).
  - Characters that are not valid in group names become C(_), so
    C(prod-east) becomes C(cluster_prod_east). Two clusters that end up with
    the same group name fail the sync.
  - Any API error fails the sync, and so does an API that returns no
    clusters (unless O(allow_empty) is on). A failed sync leaves the AAP
    inventory as it was, so Overwrite never deletes hosts because of an
    outage.
  - The config file must be named C(cluster_api.yml) or end in
    C(.cluster_api.yml).
extends_documentation_fragment:
  - constructed
options:
  plugin:
    description: Marks the file as config for this plugin.
    required: true
    choices: [cluster_api]
  api_url:
    description:
      - Base URL of the cluster API. The plugin calls C(GET <api_url>/clusters).
      - When unset, the plugin reads O(clusters_file) instead.
    type: str
    env:
      - name: CLUSTER_API_URL
  api_token:
    description: Bearer token for the cluster API.
    type: str
    env:
      - name: CLUSTER_API_TOKEN
  validate_certs:
    description: Verify the cluster API's TLS certificate.
    type: bool
    default: true
  timeout:
    description: Seconds to wait for the cluster API.
    type: int
    default: 30
  clusters_file:
    description:
      - Mock API response used when O(api_url) is unset. Relative paths are
        resolved from the config file's folder.
    type: str
    default: clusters.json
  allow_empty:
    description:
      - Accept an API response with no clusters. Leave off, so an API that
        wrongly returns nothing can't empty the inventory.
    type: bool
    default: false
"""

EXAMPLES = r"""
# cluster_api.yml
plugin: cluster_api
api_url: https://cmdb.example.com/api
keyed_groups:
  - key: site
    prefix: site
"""

import json
import os
import re

from ansible.errors import AnsibleParserError
from ansible.module_utils.common.text.converters import to_native
from ansible.module_utils.urls import open_url
from ansible.plugins.inventory import BaseInventoryPlugin, Constructable


class InventoryModule(BaseInventoryPlugin, Constructable):
    NAME = "cluster_api"

    def verify_file(self, path):
        return super().verify_file(path) and path.endswith(
            ("cluster_api.yml", "cluster_api.yaml")
        )

    def parse(self, inventory, loader, path, cache=True):
        super().parse(inventory, loader, path, cache)
        self._read_config_data(path)
        self._config_dir = os.path.dirname(path)

        clusters = self._fetch_clusters()
        if not clusters and not self.get_option("allow_empty"):
            raise AnsibleParserError(
                "The cluster API returned no clusters. Refusing to empty the "
                "inventory. Set allow_empty: true if that's expected."
            )
        self._populate(clusters)

    def _fetch_clusters(self):
        """Return [{"name": ..., "hosts": [{"hostname", "role", "ip"}, ...]}]."""
        api_url = self.get_option("api_url")
        if not api_url:
            path = os.path.join(self._config_dir, self.get_option("clusters_file"))
            try:
                with open(path) as f:
                    return json.load(f)["clusters"]
            except (OSError, ValueError, KeyError) as e:
                raise AnsibleParserError(f"Can't read {path}: {to_native(e)}")

        headers = {"Accept": "application/json"}
        if self.get_option("api_token"):
            headers["Authorization"] = f"Bearer {self.get_option('api_token')}"
        url = api_url.rstrip("/") + "/clusters"
        try:
            # open_url raises on any non-2xx response.
            resp = open_url(
                url,
                headers=headers,
                validate_certs=self.get_option("validate_certs"),
                timeout=self.get_option("timeout"),
            )
            return json.load(resp)["clusters"]
        except Exception as e:
            raise AnsibleParserError(f"Cluster API call to {url} failed: {to_native(e)}")

    def _populate(self, clusters):
        seen = {}
        for cluster in clusters:
            name = cluster["name"]
            group = self.inventory.add_group("cluster_" + re.sub(r"[^A-Za-z0-9_]", "_", name))
            if group in seen:
                raise AnsibleParserError(
                    f"Clusters {seen[group]!r} and {name!r} both map to group {group}."
                )
            seen[group] = name
            self.inventory.set_variable(group, "cluster_name", name)

            for host in cluster["hosts"]:
                hostname = host["hostname"]
                role = self.inventory.add_group(re.sub(r"[^A-Za-z0-9_]", "_", host["role"]))
                self.inventory.add_host(hostname, group=group)
                self.inventory.add_child(role, hostname)

                hostvars = {
                    "ansible_host": host["ip"],
                    "host_ip": host["ip"],
                    "role": host["role"],
                    "cluster_name": name,
                }
                for key, value in hostvars.items():
                    self.inventory.set_variable(hostname, key, value)

                strict = self.get_option("strict")
                self._set_composite_vars(self.get_option("compose"), hostvars, hostname, strict=strict)
                self._add_host_to_composed_groups(self.get_option("groups"), hostvars, hostname, strict=strict)
                self._add_host_to_keyed_groups(self.get_option("keyed_groups"), hostvars, hostname, strict=strict)
