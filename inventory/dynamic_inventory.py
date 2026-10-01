#!/usr/bin/env python3
"""
Minimal Ansible dynamic inventory script.

Ansible calls this script with:
    --list          -> return all groups and hosts as JSON
    --host <name>   -> return vars for one host (we return {} because
                       all host vars are already in _meta.hostvars)

Inputs come from ENVIRONMENT VARIABLES, not extra_vars. In AWX, set these in
the Inventory Source's "Source variables" field (or inject them with a
custom credential type):

    INV_ENVIRONMENT   dev | prod        (default: dev)
    INV_WEB_COUNT     number of web hosts to generate (default: 2)
    INV_API_TOKEN     optional secret, e.g. for calling a CMDB API. Here we
                      only report whether it was set; we never output it.
"""
import argparse
import json
import os


def build_inventory():
    # `or` handles variables that are set but empty (common with injectors).
    env = os.environ.get("INV_ENVIRONMENT") or "dev"
    web_count = int(os.environ.get("INV_WEB_COUNT") or "2")
    api_token_present = bool(os.environ.get("INV_API_TOKEN"))

    web_hosts = [f"{env}-web-{i:02d}" for i in range(1, web_count + 1)]
    db_hosts = [f"{env}-db-01"]

    hostvars = {}
    for name in web_hosts + db_hosts:
        hostvars[name] = {
            # Run against localhost so the example works with no real servers.
            "ansible_connection": "local",
            "role": "web" if "-web-" in name else "db",
        }

    return {
        "all": {
            "children": ["web", "db"],
            "vars": {
                "environment_name": env,
                "api_token_present": api_token_present,
            },
        },
        "web": {"hosts": web_hosts},
        "db": {"hosts": db_hosts},
        "_meta": {"hostvars": hostvars},
    }


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
