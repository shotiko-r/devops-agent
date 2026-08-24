import config

from .subprocess_utils import run_bounded


def run_kubectl(args):
    """Run a read-only kubectl command."""

    return run_bounded(
        ["kubectl", *args],
        timeout=config.KUBERNETES_TIMEOUT_SECONDS,
        error_label="Kubernetes",
    )


def kubernetes_nodes():
    """Show Kubernetes cluster nodes."""

    return run_kubectl(["get", "nodes"])


def kubernetes_pods(namespace=""):
    """Show Kubernetes pods."""

    if namespace:
        return run_kubectl(["get", "pods", "-n", namespace])

    return run_kubectl(["get", "pods", "-A"])


def kubernetes_deployments(namespace=""):
    """Show Kubernetes deployments."""

    if namespace:
        return run_kubectl(["get", "deployments", "-n", namespace])

    return run_kubectl(["get", "deployments", "-A"])


def kubernetes_services(namespace=""):
    """Show Kubernetes services."""

    if namespace:
        return run_kubectl(["get", "services", "-n", namespace])

    return run_kubectl(["get", "services", "-A"])


def kubernetes_namespaces():
    """Show Kubernetes namespaces."""

    return run_kubectl(["get", "namespaces"])


def kubernetes_logs(pod, namespace=""):
    """Show logs from a Kubernetes pod."""

    args = ["logs", pod]

    if namespace:
        args.extend(["-n", namespace])

    return run_kubectl(args)


def kubernetes_describe(resource, name, namespace=""):
    """Describe a Kubernetes resource."""

    args = ["describe", resource, name]

    if namespace:
        args.extend(["-n", namespace])

    return run_kubectl(args)