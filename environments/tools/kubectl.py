"""kubectl tools - Kubernetes cluster management via kubectl CLI.

Provides tools for interacting with Kubernetes clusters using the kubectl CLI.
Supports common operations like getting pods, logs, events, and describing resources.

Authentication:
- KUBECONFIG: Path to kubeconfig file (default: ~/.kube/config)
- KUBECONFIG_B64: Base64-encoded kubeconfig (for containerized environments)
- KUBE_CONTEXT: Optional context to use (overrides kubeconfig default)

For remote environments, encode your kubeconfig:
    base64 -w 0 ~/.kube/config > kubeconfig.b64
Then set KUBECONFIG_B64 to the contents.
"""

import asyncio
import base64
import json
import logging
import os
import shutil
import tempfile
from typing import Any

from hud.server import MCPRouter

logger = logging.getLogger(__name__)

router = MCPRouter(name="kubectl")

# Kubernetes configuration
KUBECONFIG = os.getenv("KUBECONFIG", os.path.expanduser("~/.kube/config"))
KUBECONFIG_B64 = os.getenv("KUBECONFIG_B64", "")
KUBE_CONTEXT = os.getenv("KUBE_CONTEXT", "")

# If base64 kubeconfig is provided, decode it to a temp file
_temp_kubeconfig: str | None = None


def _get_kubeconfig() -> str:
    """Get the kubeconfig path, decoding from base64 if needed."""
    global _temp_kubeconfig
    
    if KUBECONFIG_B64 and not _temp_kubeconfig:
        # Decode base64 kubeconfig to temp file
        try:
            decoded = base64.b64decode(KUBECONFIG_B64)
            fd, _temp_kubeconfig = tempfile.mkstemp(suffix=".yaml", prefix="kubeconfig-")
            with os.fdopen(fd, "wb") as f:
                f.write(decoded)
            logger.info("Decoded kubeconfig to %s", _temp_kubeconfig)
        except Exception as e:
            logger.error("Failed to decode KUBECONFIG_B64: %s", e)
            return KUBECONFIG
        return _temp_kubeconfig
    
    return _temp_kubeconfig or KUBECONFIG


async def _run_kubectl(args: list[str], namespace: str | None = None) -> str:
    """Run a kubectl command and return the output."""
    kubectl_path = shutil.which("kubectl")
    if not kubectl_path:
        return "Error: kubectl not installed"
    
    cmd = [kubectl_path]
    
    # Add kubeconfig
    kubeconfig = _get_kubeconfig()
    if os.path.exists(kubeconfig):
        cmd.extend(["--kubeconfig", kubeconfig])
    
    # Add context if specified
    if KUBE_CONTEXT:
        cmd.extend(["--context", KUBE_CONTEXT])
    
    # Add namespace if specified
    if namespace:
        cmd.extend(["--namespace", namespace])
    
    # Add the actual command
    cmd.extend(args)
    
    try:
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=60.0)
        
        if process.returncode != 0:
            error_msg = stderr.decode().strip()
            if "Unable to connect" in error_msg or "connection refused" in error_msg:
                return f"Error: Cannot connect to cluster. Check your kubeconfig and network.\n{error_msg}"
            return f"Error: {error_msg}"
        
        return stdout.decode()
    except asyncio.TimeoutError:
        return "Error: kubectl command timed out after 60 seconds"
    except Exception as e:
        return f"Error executing kubectl: {e}"


# =============================================================================
# TOOLS
# =============================================================================


@router.tool()
async def kubectl_get_pods(
    namespace: str = "default",
    selector: str | None = None,
    all_namespaces: bool = False,
) -> str:
    """Get pods in a namespace or across all namespaces.
    
    Args:
        namespace: Kubernetes namespace (default: "default")
        selector: Optional label selector (e.g., "app=nginx")
        all_namespaces: If True, get pods across all namespaces
    
    Returns pod list with status, restarts, and age.
    """
    args = ["get", "pods", "-o", "wide"]
    
    if all_namespaces:
        args.append("--all-namespaces")
        namespace = None
    
    if selector:
        args.extend(["-l", selector])
    
    output = await _run_kubectl(args, namespace)
    return f"# Pods\n\n```\n{output}\n```"


@router.tool()
async def kubectl_get_deployments(
    namespace: str = "default",
    all_namespaces: bool = False,
) -> str:
    """Get deployments in a namespace.
    
    Args:
        namespace: Kubernetes namespace (default: "default")
        all_namespaces: If True, get across all namespaces
    
    Returns deployment list with replica counts and status.
    """
    args = ["get", "deployments", "-o", "wide"]
    
    if all_namespaces:
        args.append("--all-namespaces")
        namespace = None
    
    output = await _run_kubectl(args, namespace)
    return f"# Deployments\n\n```\n{output}\n```"


@router.tool()
async def kubectl_get_services(
    namespace: str = "default",
    all_namespaces: bool = False,
) -> str:
    """Get services in a namespace.
    
    Args:
        namespace: Kubernetes namespace (default: "default")
        all_namespaces: If True, get across all namespaces
    
    Returns service list with type, cluster IP, and ports.
    """
    args = ["get", "services", "-o", "wide"]
    
    if all_namespaces:
        args.append("--all-namespaces")
        namespace = None
    
    output = await _run_kubectl(args, namespace)
    return f"# Services\n\n```\n{output}\n```"


@router.tool()
async def kubectl_describe_pod(
    pod_name: str,
    namespace: str = "default",
) -> str:
    """Get detailed information about a pod.
    
    Args:
        pod_name: Name of the pod
        namespace: Kubernetes namespace (default: "default")
    
    Returns detailed pod information including events, conditions, and containers.
    """
    args = ["describe", "pod", pod_name]
    output = await _run_kubectl(args, namespace)
    return f"# Pod: {pod_name}\n\n```\n{output}\n```"


@router.tool()
async def kubectl_get_logs(
    pod_name: str,
    namespace: str = "default",
    container: str | None = None,
    tail: int = 100,
    previous: bool = False,
) -> str:
    """Get logs from a pod.
    
    Args:
        pod_name: Name of the pod
        namespace: Kubernetes namespace (default: "default")
        container: Container name (required for multi-container pods)
        tail: Number of lines to return (default: 100)
        previous: If True, get logs from previous container instance
    
    Returns the pod's container logs.
    """
    args = ["logs", pod_name, "--tail", str(tail)]
    
    if container:
        args.extend(["-c", container])
    
    if previous:
        args.append("--previous")
    
    output = await _run_kubectl(args, namespace)
    
    if not output.strip():
        return f"No logs available for pod {pod_name}"
    
    return f"# Logs: {pod_name}\n\n```\n{output}\n```"


@router.tool()
async def kubectl_get_events(
    namespace: str = "default",
    all_namespaces: bool = False,
    field_selector: str | None = None,
) -> str:
    """Get cluster events.
    
    Args:
        namespace: Kubernetes namespace (default: "default")
        all_namespaces: If True, get events across all namespaces
        field_selector: Optional field selector (e.g., "type=Warning")
    
    Returns recent cluster events sorted by timestamp.
    """
    args = ["get", "events", "--sort-by=.lastTimestamp"]
    
    if all_namespaces:
        args.append("--all-namespaces")
        namespace = None
    
    if field_selector:
        args.extend(["--field-selector", field_selector])
    
    output = await _run_kubectl(args, namespace)
    return f"# Events\n\n```\n{output}\n```"


@router.tool()
async def kubectl_get_nodes() -> str:
    """Get all cluster nodes.
    
    Returns node list with status, roles, age, and version.
    """
    args = ["get", "nodes", "-o", "wide"]
    output = await _run_kubectl(args)
    return f"# Nodes\n\n```\n{output}\n```"


@router.tool()
async def kubectl_top_pods(
    namespace: str = "default",
    all_namespaces: bool = False,
) -> str:
    """Get CPU and memory usage for pods (requires metrics-server).
    
    Args:
        namespace: Kubernetes namespace (default: "default")
        all_namespaces: If True, get across all namespaces
    
    Returns resource usage for pods.
    """
    args = ["top", "pods"]
    
    if all_namespaces:
        args.append("--all-namespaces")
        namespace = None
    
    output = await _run_kubectl(args, namespace)
    return f"# Pod Resource Usage\n\n```\n{output}\n```"


@router.tool()
async def kubectl_top_nodes() -> str:
    """Get CPU and memory usage for nodes (requires metrics-server).
    
    Returns resource usage for all cluster nodes.
    """
    args = ["top", "nodes"]
    output = await _run_kubectl(args)
    return f"# Node Resource Usage\n\n```\n{output}\n```"


@router.tool()
async def kubectl_rollout_status(
    resource: str,
    name: str,
    namespace: str = "default",
) -> str:
    """Check rollout status of a deployment/daemonset/statefulset.
    
    Args:
        resource: Resource type (deployment, daemonset, statefulset)
        name: Name of the resource
        namespace: Kubernetes namespace (default: "default")
    
    Returns the rollout status.
    """
    args = ["rollout", "status", f"{resource}/{name}"]
    output = await _run_kubectl(args, namespace)
    return f"# Rollout Status: {resource}/{name}\n\n{output}"


# NOTE: kubectl_rollout_restart removed - this environment is READ ONLY


@router.tool()
async def kubectl_get_configmaps(
    namespace: str = "default",
) -> str:
    """Get configmaps in a namespace.
    
    Args:
        namespace: Kubernetes namespace (default: "default")
    
    Returns list of configmaps.
    """
    args = ["get", "configmaps"]
    output = await _run_kubectl(args, namespace)
    return f"# ConfigMaps\n\n```\n{output}\n```"


@router.tool()
async def kubectl_get_secrets(
    namespace: str = "default",
) -> str:
    """Get secrets in a namespace (names only, no values).
    
    Args:
        namespace: Kubernetes namespace (default: "default")
    
    Returns list of secrets (values are not shown for security).
    """
    args = ["get", "secrets"]
    output = await _run_kubectl(args, namespace)
    return f"# Secrets\n\n```\n{output}\n```"


@router.tool()
async def kubectl_get_resource_yaml(
    resource_type: str,
    name: str,
    namespace: str = "default",
) -> str:
    """Get a resource's YAML definition.
    
    Args:
        resource_type: Type of resource (pod, deployment, service, etc.)
        name: Name of the resource
        namespace: Kubernetes namespace (default: "default")
    
    Returns the full YAML definition of the resource.
    """
    args = ["get", resource_type, name, "-o", "yaml"]
    output = await _run_kubectl(args, namespace)
    return f"# {resource_type}/{name}\n\n```yaml\n{output}\n```"


# NOTE: kubectl_scale and kubectl_exec removed - this environment is READ ONLY

