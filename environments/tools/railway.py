"""Railway GraphQL API tools for ops diagnostics.

Focuses on finding services and getting logs for troubleshooting.
API Docs: https://docs.railway.app/reference/public-api
"""

import json
import os
from typing import Any

import httpx

from hud.server import MCPRouter

router = MCPRouter()

RAILWAY_API_URL = "https://backboard.railway.com/graphql/v2"


def _graphql_request(query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
    """Execute a GraphQL request to Railway API."""
    token = os.getenv("RAILWAY_API_TOKEN")
    if not token:
        return {"error": "RAILWAY_API_TOKEN not set"}
    
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    
    payload = {"query": query}
    if variables:
        payload["variables"] = variables
    
    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.post(RAILWAY_API_URL, headers=headers, json=payload)
            response.raise_for_status()
            return response.json()
    except httpx.HTTPStatusError as e:
        return {"error": f"HTTP {e.response.status_code}: {e.response.text}"}
    except Exception as e:
        return {"error": str(e)}


@router.tool()
async def railway_list_projects() -> str:
    """List all Railway projects with their services and environments."""
    query = """
    query {
        projects {
            edges {
                node {
                    id
                    name
                    description
                    updatedAt
                    environments {
                        edges {
                            node {
                                id
                                name
                            }
                        }
                    }
                    services {
                        edges {
                            node {
                                id
                                name
                                icon
                            }
                        }
                    }
                }
            }
        }
    }
    """
    result = _graphql_request(query)
    return json.dumps(result, indent=2)


@router.tool()
async def railway_get_service(service_id: str) -> str:
    """Get detailed info about a specific service including recent deployments.
    
    Args:
        service_id: The service ID (get from railway_list_projects)
    """
    query = """
    query($id: String!) {
        service(id: $id) {
            id
            name
            icon
            createdAt
            updatedAt
            deployments(first: 5) {
                edges {
                    node {
                        id
                        status
                        createdAt
                        meta
                    }
                }
            }
        }
    }
    """
    result = _graphql_request(query, {"id": service_id})
    return json.dumps(result, indent=2)


@router.tool()
async def railway_get_deployments(
    project_id: str,
    limit: int = 10,
) -> str:
    """Get recent deployments for a project.
    
    Args:
        project_id: The project ID
        limit: Number of deployments to return (default: 10)
    """
    query = """
    query($first: Int) {
        deployments(first: $first) {
            edges {
                node {
                    id
                    status
                    createdAt
                    staticUrl
                    meta
                    service {
                        id
                        name
                    }
                    environment {
                        id
                        name
                    }
                }
            }
        }
    }
    """
    result = _graphql_request(query, {"first": limit})
    return json.dumps(result, indent=2)


@router.tool()
async def railway_get_deployment_logs(
    deployment_id: str,
    limit: int = 100,
) -> str:
    """Get logs for a specific deployment. Critical for debugging.
    
    Args:
        deployment_id: The deployment ID (get from railway_get_deployments)
        limit: Number of log lines (default: 100)
    """
    query = """
    query($deploymentId: String!, $limit: Int) {
        deploymentLogs(deploymentId: $deploymentId, limit: $limit) {
            message
            timestamp
            severity
        }
    }
    """
    result = _graphql_request(query, {"deploymentId": deployment_id, "limit": limit})
    return json.dumps(result, indent=2)


@router.tool()
async def railway_get_build_logs(
    deployment_id: str,
    limit: int = 100,
) -> str:
    """Get build logs for a deployment. Useful for debugging build failures.
    
    Args:
        deployment_id: The deployment ID
        limit: Number of log lines (default: 100)
    """
    query = """
    query($deploymentId: String!, $limit: Int) {
        buildLogs(deploymentId: $deploymentId, limit: $limit) {
            message
            timestamp
        }
    }
    """
    result = _graphql_request(query, {"deploymentId": deployment_id, "limit": limit})
    return json.dumps(result, indent=2)


@router.tool()
async def railway_get_deployment(deployment_id: str) -> str:
    """Get detailed info about a specific deployment.
    
    Args:
        deployment_id: The deployment ID
    """
    query = """
    query($id: String!) {
        deployment(id: $id) {
            id
            status
            createdAt
            updatedAt
            staticUrl
            meta
            service {
                id
                name
            }
            environment {
                id
                name
            }
        }
    }
    """
    result = _graphql_request(query, {"id": deployment_id})
    return json.dumps(result, indent=2)


@router.tool()
async def railway_get_variables(
    project_id: str,
    environment_id: str,
    service_id: str | None = None,
) -> str:
    """Get environment variables. Useful for checking config issues.
    
    Args:
        project_id: The project ID
        environment_id: The environment ID
        service_id: Optional service ID for service-specific vars
    """
    query = """
    query($projectId: String!, $environmentId: String!, $serviceId: String) {
        variables(projectId: $projectId, environmentId: $environmentId, serviceId: $serviceId)
    }
    """
    result = _graphql_request(query, {
        "projectId": project_id,
        "environmentId": environment_id,
        "serviceId": service_id,
    })
    return json.dumps(result, indent=2)


# NOTE: Mutation tools (redeploy, restart) removed - this environment is READ ONLY


@router.tool()
async def railway_get_service_instances(service_id: str) -> str:
    """Get all instances of a service across environments.
    
    Args:
        service_id: The service ID
    """
    query = """
    query($id: String!) {
        service(id: $id) {
            id
            name
            serviceInstances {
                edges {
                    node {
                        id
                        startCommand
                        numReplicas
                        healthcheckPath
                        sleepApplication
                        railpackVersion
                        restartPolicyType
                    }
                }
            }
        }
    }
    """
    result = _graphql_request(query, {"id": service_id})
    return json.dumps(result, indent=2)


@router.tool()
async def railway_platform_status() -> str:
    """Check Railway platform status for outages."""
    query = """
    query {
        platformStatus {
            status
            incidents {
                url
                message
                updatedAt
            }
            maintenances {
                url
                message
                scheduledFor
            }
        }
    }
    """
    result = _graphql_request(query)
    return json.dumps(result, indent=2)
