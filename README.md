# AAP dynamic inventory + playbook example

Shows how values get from an AAP job template into the inventory script and
the playbook.

```
inventory/dynamic_inventory.py     # dynamic inventory script (reads env vars)
playbook.yml                       # playbook (reads extra vars, inventory vars, env vars)
aap/credential_type_inputs.yml     # paste into a Credential Type: Input configuration
aap/credential_type_injectors.yml  # paste into a Credential Type: Injector configuration
aap/survey_spec.json               # survey for the job template (UI reference or API)
```

## How values get in

| Input goes to... | How you set it in AAP | How the code reads it |
|---|---|---|
| Inventory script | Inventory Source → **Source variables**, or a credential on the **inventory source** | `os.environ[...]` |
| Playbook, as variables | Job Template → **Variables**, **Survey**, **Prompt on launch** (extra vars) | `{{ var_name }}` |
| Playbook, as env vars | A credential on the **job template** | `lookup('env', 'VAR')` |
| Tasks, as env vars from extra vars | `environment:` keyword in the play | `$VAR` in commands |

**Job template extra vars and credentials do not reach the inventory script.**
AAP syncs the inventory as a separate job before the playbook runs, and that
job uses only the inventory source's own settings and credentials.

## Run it locally

```bash
INV_ENVIRONMENT=prod INV_WEB_COUNT=3 ./inventory/dynamic_inventory.py --list
ansible-inventory -i inventory/dynamic_inventory.py --graph

INV_ENVIRONMENT=prod INV_API_TOKEN=abc ansible-playbook \
  -i inventory/dynamic_inventory.py playbook.yml \
  -e target_group=web -e greeting="Hi from the CLI" -e target_env=prod
```

## Push to Git

The script must be executable in Git, or the inventory sync fails. On Windows:

```bash
git add .
git update-index --chmod=+x inventory/dynamic_inventory.py
git commit -m "AAP dynamic inventory example"
```

## Set it up in AAP

### 1. Project
Create a Project that points to this Git repo and sync it.

### 2. Credential type
**Administration → Credential Types → Add**, name it `Demo Inventory Env`.
- Input configuration: contents of [aap/credential_type_inputs.yml](aap/credential_type_inputs.yml)
- Injector configuration: contents of [aap/credential_type_injectors.yml](aap/credential_type_injectors.yml)

### 3. Credentials
**Resources → Credentials → Add**, type `Demo Inventory Env`. Create two:

| Name | Environment name | Number of web hosts | API token |
|---|---|---|---|
| `demo-env-dev` | dev | 2 | any test value |
| `demo-env-prod` | prod | 3 | any test value |

### 4. Inventory and source
Create an Inventory `demo-dynamic`, then **Sources → Add**:
- Source: **Sourced from a Project**, the project from step 1
- Inventory file: `inventory/dynamic_inventory.py`
- Credential: `demo-env-prod` (this sets the script's env vars)
- Turn on **Overwrite** and **Update on launch**

You can use **Source variables** instead of a credential for non-secret
values, e.g. `INV_ENVIRONMENT: prod`. Save and **Sync**. You should see hosts
`prod-web-01..03` and `prod-db-01`, and the `all` group should have
`api_token_present: true`.

### 5. Job template
- Inventory `demo-dynamic`, the project, playbook `playbook.yml`
- Credentials: `demo-env-dev`, with **Prompt on launch** turned on
- Survey: add the three questions from [aap/survey_spec.json](aap/survey_spec.json)
  (`target_group`, `greeting`, `target_env`) and turn the survey on

To load the survey through the API instead of the UI:
```bash
curl -k -u admin:PASSWORD -H "Content-Type: application/json" \
  -X POST https://AAP_HOST/api/controller/v2/job_templates/<ID>/survey_spec/ \
  -d @aap/survey_spec.json
```
On AWX or AAP 2.4 and earlier the path is `/api/v2/...`.

### 6. Launch and check the output
| Task | What it shows | Source |
|---|---|---|
| Show values from the job... | `greeting`, `target_group`, `role`, `environment_name` | survey + inventory |
| Show env vars injected... | `INV_ENVIRONMENT=dev` | the credential on the job template |
| Print it | `DEMO_TARGET_ENV=<survey answer>` | survey → `environment:` |

Hosts will say `prod-...` while `INV_ENVIRONMENT` in the job says `dev`. That
is expected: the inventory sync used the inventory source's credential, and
the playbook used the job template's credential. Switch the credential at
launch to `demo-env-prod` to see the playbook value change.

## Precedence
Extra vars beat everything else. If the job template, survey, and launch
prompt all set `greeting`, the launch-time value wins, and extra vars override
inventory vars with the same name.
