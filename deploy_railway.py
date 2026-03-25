"""
Deploy the Neuraivex Client Portal to Railway.
Creates a new 'Client Portal' environment inside the existing illustrious-dream project,
creates a 'client-portal' service, links GitHub repo, sets env vars, and generates a domain.

Usage:
  python deploy_railway.py --create     # Full first-time deploy
  python deploy_railway.py --env        # Push/update env vars only
  python deploy_railway.py --status     # Get URL
"""

import os
import sys
import json
import argparse
import requests
from pathlib import Path

# ── Load env from parent .env ──────────────────────────────────────────────
def load_env():
    for env_path in [Path(__file__).parent / ".env", Path(__file__).parent.parent / ".env"]:
        if env_path.exists():
            for line in env_path.read_text().splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, val = line.split("=", 1)
                    os.environ.setdefault(key.strip(), val.strip())

load_env()

RAILWAY_API_TOKEN  = os.environ.get("RAILWAY_API_TOKEN", "")
RAILWAY_PROJECT_ID = os.environ.get("RAILWAY_PROJECT_ID", "")
RAILWAY_API_URL    = "https://backboard.railway.app/graphql/v2"

SERVICE_NAME  = "client-portal"
ENV_NAME      = "Client Portal"
GITHUB_REPO   = "nicholaswatkins222-oss/neuraivex-client-portal"
GITHUB_BRANCH = "master"


def _gql(query: str, variables: dict = None) -> dict:
    resp = requests.post(
        RAILWAY_API_URL,
        json={"query": query, "variables": variables or {}},
        headers={"Authorization": f"Bearer {RAILWAY_API_TOKEN}", "Content-Type": "application/json"},
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    if "errors" in data:
        raise RuntimeError(f"Railway GraphQL error: {json.dumps(data['errors'], indent=2)}")
    return data.get("data", {})


def get_all_environments() -> list:
    query = """
    query GetEnvironments($projectId: String!) {
        project(id: $projectId) {
            environments { edges { node { id name } } }
        }
    }
    """
    data = _gql(query, {"projectId": RAILWAY_PROJECT_ID})
    return data.get("project", {}).get("environments", {}).get("edges", [])


def get_environment_id(name: str) -> str | None:
    for edge in get_all_environments():
        node = edge["node"]
        if node["name"] == name:
            return node["id"]
    return None


def create_environment(name: str) -> str:
    mutation = """
    mutation EnvironmentCreate($input: EnvironmentCreateInput!) {
        environmentCreate(input: $input) { id name }
    }
    """
    data = _gql(mutation, {"input": {"projectId": RAILWAY_PROJECT_ID, "name": name}})
    return data["environmentCreate"]["id"]


def get_service_id(env_id: str) -> str | None:
    query = """
    query GetServices($projectId: String!) {
        project(id: $projectId) {
            services { edges { node { id name } } }
        }
    }
    """
    data = _gql(query, {"projectId": RAILWAY_PROJECT_ID})
    for edge in data.get("project", {}).get("services", {}).get("edges", []):
        if edge["node"]["name"] == SERVICE_NAME:
            return edge["node"]["id"]
    return None


def create_service() -> str:
    mutation = """
    mutation ServiceCreate($input: ServiceCreateInput!) {
        serviceCreate(input: $input) { id name }
    }
    """
    data = _gql(mutation, {"input": {"projectId": RAILWAY_PROJECT_ID, "name": SERVICE_NAME}})
    return data["serviceCreate"]["id"]


def connect_github(service_id: str, env_id: str):
    mutation = """
    mutation ServiceSourceUpdate($id: String!, $input: ServiceUpdateInput!) {
        serviceUpdate(id: $id, input: $input) { id }
    }
    """
    _gql(mutation, {
        "id": service_id,
        "input": {
            "source": {
                "repo": GITHUB_REPO,
                "branch": GITHUB_BRANCH,
            }
        }
    })


def set_env_vars(service_id: str, env_id: str):
    # Generate fresh keys for production
    secret_key = os.urandom(32).hex()
    fernet_key = os.environ.get("FERNET_KEY", "")  # reuse local key or generate new

    vars_to_set = {
        "SECRET_KEY": secret_key,
        "FERNET_KEY": fernet_key,
        "FLASK_ENV": "production",
        "DATABASE_URL": "sqlite:///portal.db",
    }

    mutation = """
    mutation VariableUpsert($input: VariableUpsertInput!) {
        variableUpsert(input: $input)
    }
    """
    for key, val in vars_to_set.items():
        if not val:
            print(f"  SKIP {key} — not set")
            continue
        _gql(mutation, {"input": {
            "projectId": RAILWAY_PROJECT_ID,
            "environmentId": env_id,
            "serviceId": service_id,
            "name": key,
            "value": val,
        }})
        masked = val[:6] + "..." if len(val) > 6 else val
        print(f"  Set {key} = {masked}")

    return vars_to_set


def create_domain(service_id: str, env_id: str) -> str | None:
    mutation = """
    mutation ServiceDomainCreate($input: ServiceDomainCreateInput!) {
        serviceDomainCreate(input: $input) { domain }
    }
    """
    try:
        data = _gql(mutation, {"input": {"serviceId": service_id, "environmentId": env_id}})
        domain = data.get("serviceDomainCreate", {}).get("domain", "")
        return f"https://{domain}" if domain else None
    except Exception as e:
        print(f"  WARNING: Could not auto-create domain: {e}")
        return None


def get_domain(service_id: str, env_id: str) -> str | None:
    query = """
    query GetDomains($serviceId: String!, $environmentId: String!) {
        serviceDomains(serviceId: $serviceId, environmentId: $environmentId) {
            edges { node { domain } }
        }
    }
    """
    try:
        data = _gql(query, {"serviceId": service_id, "environmentId": env_id})
        edges = data.get("serviceDomains", {}).get("edges", [])
        if edges:
            return f"https://{edges[0]['node']['domain']}"
    except Exception:
        pass
    return None


# ── CLI commands ───────────────────────────────────────────────────────────

def cmd_create():
    if not RAILWAY_API_TOKEN or not RAILWAY_PROJECT_ID:
        print("ERROR: RAILWAY_API_TOKEN and RAILWAY_PROJECT_ID must be set")
        sys.exit(1)

    # 1. Environment
    print(f"Checking for '{ENV_NAME}' environment...")
    env_id = get_environment_id(ENV_NAME)
    if env_id:
        print(f"  Already exists: {env_id}")
    else:
        print(f"  Creating...")
        env_id = create_environment(ENV_NAME)
        print(f"  Created: {env_id}")

    # 2. Service
    print(f"\nChecking for '{SERVICE_NAME}' service...")
    service_id = get_service_id(env_id)
    if service_id:
        print(f"  Already exists: {service_id}")
    else:
        print(f"  Creating...")
        service_id = create_service()
        print(f"  Created: {service_id}")

    # 3. GitHub connection
    print(f"\nConnecting to GitHub repo: {GITHUB_REPO}...")
    try:
        connect_github(service_id, env_id)
        print(f"  Connected (branch: {GITHUB_BRANCH})")
    except Exception as e:
        print(f"  WARNING: {e}")
        print(f"  Connect manually in Railway dashboard: Deployments > Connect Repo")

    # 4. Env vars
    print(f"\nSetting environment variables...")
    deployed_vars = set_env_vars(service_id, env_id)

    # 5. Domain
    print(f"\nGenerating domain...")
    url = get_domain(service_id, env_id) or create_domain(service_id, env_id)
    if url:
        print(f"  URL: {url}")
    else:
        print(f"  No domain yet — generate one in Railway dashboard")

    print(f"\n{'='*50}")
    print(f"DEPLOYED to Railway environment: {ENV_NAME}")
    print(f"Service: {SERVICE_NAME} ({service_id})")
    print(f"Environment ID: {env_id}")
    if url:
        print(f"URL: {url}")
    print(f"\nIMPORTANT — Save these in your .env:")
    print(f"  PORTAL_FERNET_KEY={deployed_vars.get('FERNET_KEY', '')}")
    print(f"  PORTAL_SECRET_KEY={deployed_vars.get('SECRET_KEY', '')}")
    print(f"\nAfter first deploy, run seed.py via Railway console to create admin user.")
    print(f"Monitor at: railway.app/project/{RAILWAY_PROJECT_ID}")


def cmd_env():
    if not RAILWAY_API_TOKEN:
        print("ERROR: RAILWAY_API_TOKEN not set")
        sys.exit(1)

    env_id = get_environment_id(ENV_NAME)
    if not env_id:
        print(f"Environment '{ENV_NAME}' not found. Run --create first.")
        sys.exit(1)

    service_id = get_service_id(env_id)
    if not service_id:
        print(f"Service '{SERVICE_NAME}' not found. Run --create first.")
        sys.exit(1)

    print(f"Pushing env vars to {SERVICE_NAME}...")
    set_env_vars(service_id, env_id)
    print("Done.")


def cmd_status():
    env_id = get_environment_id(ENV_NAME)
    if not env_id:
        print(f"Environment '{ENV_NAME}' not found.")
        return
    service_id = get_service_id(env_id)
    if not service_id:
        print(f"Service '{SERVICE_NAME}' not found.")
        return
    url = get_domain(service_id, env_id)
    print(f"Service: {SERVICE_NAME} ({service_id})")
    print(f"Environment: {ENV_NAME} ({env_id})")
    print(f"URL: {url or 'not assigned'}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Deploy Neuraivex Client Portal to Railway")
    parser.add_argument("--create", action="store_true", help="Full first-time deploy")
    parser.add_argument("--env",    action="store_true", help="Push env vars only")
    parser.add_argument("--status", action="store_true", help="Get service URL")
    args = parser.parse_args()

    if args.create:   cmd_create()
    elif args.env:    cmd_env()
    elif args.status: cmd_status()
    else:             parser.print_help()
