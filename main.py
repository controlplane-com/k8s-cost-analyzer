"""
; Control Plane - K8s Cost Analyzer

; This script belongs to this repository: https://github.com/controlplane-com/k8s-cost-analyzer
; Make sure you meet the prerequisites there before running the script
"""

import os
import re
import sys
import time
import json
import signal
import random
import select
import certifi
import colorama
import threading
import platform
import subprocess
import requests


### Classes ###
class LoadingAnimation:
    def __init__(self):
        self._is_loading = False
        self.description = ""
        self.temp_description = ""
        self.loading_thread = None

    # Public Methods #
    def start_loading(self, description):
        self.description = description
        if not self._is_loading:
            self._is_loading = True
            self.loading_thread = threading.Thread(target=self._loading_animation)
            self.loading_thread.start()

    def stop_loading(self) -> None:
        if self._is_loading:
            self._is_loading = False
            self.loading_thread.join()
            self.loading_thread = None
            clear_console_line(self.temp_description)

    # Private Methods #
    def _loading_animation(self) -> None:
        i = 0
        animation = "|/-\\"
        while self._is_loading:
            self.temp_description = (
                "[" + animation[i % len(animation)] + "] " + self.description
            )
            print_progress(self.temp_description)
            time.sleep(0.1)
            i += 1


class NodeUsageConsumption:
    def __init__(self, cpu, memory, requests_cpu, requests_memory):
        self.cpu = cpu
        self.memory = memory
        self.requests_cpu = requests_cpu
        self.requests_memory = requests_memory

    def __repr__(self) -> str:
        return f"NodeUsageConsumption(cpu={self.cpu}, memory={self.memory}, requests_cpu={self.requests_cpu}, requests_memory={self.requests_memory})"


class PodUsageConsumption:
    def __init__(self, name, namespace, container, cpu, memory):
        self.name = name
        self.namespace = namespace
        self.container = container
        self.cpu = cpu
        self.memory = memory

    def __repr__(self) -> str:
        return f"PodUsageConsumption(name={self.name}, namespace={self.namespace}, container={self.container}, cpu={self.cpu}, memory={self.memory})"


class KubernetesService:
    def __init__(self, namespace, name, port):
        self.namespace = namespace
        self.name = name
        self.port = port


class Node:
    def __init__(self):
        self.name = ""
        self.explicit_price = 0.0
        self.consumbed_cpu = 0.0
        self.consumbed_memory = 0.0
        self.containers_consumbed_cpu = 0.0
        self.containers_consumed_memory = 0.0
        self.capacity_cpu = 0.0
        self.capacity_memory = 0.0
        self.allocatable_cpu = 0.0
        self.allocatable_memory = 0.0
        self.requests_cpu = ""
        self.requests_memory = ""
        self.cloud_provider = ""
        self.instance_type = ""
        self.purchase_option = ""
        self.region = ""


class Component:
    def __init__(self, name):
        self.name = name
        self.usage_cpu = 0.0
        self.usage_memory = 0.0

    def add_usage(self, cpu, memory):
        self.usage_cpu += cpu
        self.usage_memory += memory


class Application:
    def __init__(self, name, node_name):
        self.name = name
        self.node_name = node_name
        self.cpu_usage = 0.0
        self.memory_usage = 0.0


class Cluster:
    def __init__(self):
        self.name = ""
        self.kubernetes_version = ""
        self.total_usage_cpu = 0.0
        self.total_usage_memory = 0.0
        self.components = []
        self.nodes = []
        self.applications = []

    def prepare(self):
        # Convert CPU from millicores to cores
        self.total_usage_cpu /= 1000
        for component in self.components:
            component.usage_cpu /= 1000
        for application in self.applications:
            application.cpu_usage /= 1000


class Submission:
    def __init__(self, user_name, user_email, cluster):
        self.user_name = user_name
        self.user_email = user_email
        self.cluster = cluster


### Constants ###
# General
LOCAL_PORT_START = 10000
LOCAL_PORT_END = 40000
FIND_PORT_MAX_TRIES = 5
MAX_CHECK_FOR_SUCCESS_ATTEMPTS = 10
CHECK_FOR_SUCCESS_TIME_TO_WAIT_BEFORE_RETRY = 0.5  # In seconds
DEFAULT_PROMETHEUS_QUERY_PERIOD = 48
PROMETHEUS_METRICS_COLLECTION_PERIOD = f"{DEFAULT_PROMETHEUS_QUERY_PERIOD}h"
PODS_USAGE_CONSUMPTION_LIST = []
NODES_USAGE_CONSUMPTION_DICT = {}
LOADING_ANIMATION = LoadingAnimation()
CLUSTER = Cluster()
ENDPOINT = "https://pricing-calculator.controlplane.site/submit-cluster"

# Cloud Providers
CLOUD_PROVIDER_AWS = "aws"
CLOUD_PROVIDER_GCP = "gcp"
CLOUD_PROVIDER_AZURE = "azure"
CLOUD_PROVIDER_UNKNOWN = "unknown"

# Pods Top/Get Column Names
POD_NAMESPACE_COLUMN = "NAMESPACE"
POD_NAME_COLUMN = "POD"
POD_NODE_NAME_COLUMN = "NODE"
POD_CONTAINER_NAME_COLUMN = "NAME"
POD_CPU_COLUMN = "CPU(cores)"
POD_MEMORY_COLUMN = "MEMORY"
POD_LABELS_COLUMN = "LABELS"

# Nodes Top Column Names
NODE_NAME_COLUMN = "NAME"
NODE_CPU_COLUMN = "CPU(cores)"
NODE_REQUESTS_CPU_COLUMN = "CPU%"
NODE_MEMORY_COLUMN = "MEMORY(bytes)"
NODE_REQUESTS_MEMORY_COLUMN = "MEMORY%"

# Services Column Names
SERVICE_NAMESPACE_COLUMN = "NAMESPACE"
SERVICE_NAME_COLUMN = "NAME"
SERVICE_PORTS_COLUMN = "PORT(S)"

# Tables
TOP_PODS_TABLE_COLUMNS = {
    POD_NAMESPACE_COLUMN: 0,
    POD_NAME_COLUMN: 1,
    POD_CONTAINER_NAME_COLUMN: 2,
    POD_CPU_COLUMN: 3,
    POD_MEMORY_COLUMN: 4,
}

GET_PODS_TABLE_COLUMNS = {
    POD_NAMESPACE_COLUMN: 0,
    POD_NAME_COLUMN: 1,
    POD_NODE_NAME_COLUMN: 7,
    POD_LABELS_COLUMN: 10,
}

TOP_NODES_TABLE_COLUMNS = {
    NODE_NAME_COLUMN: 0,
    NODE_CPU_COLUMN: 1,
    NODE_REQUESTS_CPU_COLUMN: 2,
    NODE_MEMORY_COLUMN: 3,
    NODE_REQUESTS_MEMORY_COLUMN: 4,
}

SERVICES_TABLE_COLUMNS = {
    SERVICE_NAMESPACE_COLUMN: 0,
    SERVICE_NAME_COLUMN: 1,
    SERVICE_PORTS_COLUMN: 5,
}

# Prometheus Queries
PODS_TOTAL_CPU_USAGE_QUERY = f"sum(rate(container_cpu_usage_seconds_total[{DEFAULT_PROMETHEUS_QUERY_PERIOD}h]) * 1000) by (namespace, pod, container)"
PODS_TOTAL_MEMORY_USAGE_QUERY = f"sum(rate(container_memory_working_set_bytes[{DEFAULT_PROMETHEUS_QUERY_PERIOD}h]) / (1024 * 1024)) by (namespace, pod, container)"
NODES_TOTAL_CPU_USAGE_QUERY = f'sum(rate(node_cpu_seconds_total{{mode!="idle"}}[{DEFAULT_PROMETHEUS_QUERY_PERIOD}h]) * 1000) by (kubernetes_node_name)'
NODES_TOTAL_MEMORY_USAGE_QUERY = "sum(node_memory_MemTotal_bytes - node_memory_MemAvailable_bytes) by (kubernetes_node_name) / (1024 * 1024)"
NODES_TOTAL_CPU_USED_PERCENTAGE_QUERY = f'(1 - avg(rate(node_cpu_seconds_total{{mode="idle"}}[{DEFAULT_PROMETHEUS_QUERY_PERIOD}m])) by (kubernetes_node_name)) * 100'
NODES_TOTAL_MEMORY_USED_PERCENTAGE_QUERY = "(1 - (avg(node_memory_MemAvailable_bytes) by (kubernetes_node_name) / avg(node_memory_MemTotal_bytes) by (kubernetes_node_name))) * 100"

# Colors
BLUE = colorama.Fore.BLUE
YELLOW = colorama.Fore.YELLOW
RED = colorama.Fore.RED
GREEN = colorama.Fore.GREEN
END = colorama.Style.RESET_ALL

# Cluster Components
KUBE_SYSTEM = Component("kube_system")
CERT_MANAGER = Component("cert_manager")
NATS = Component("nats")
KNATIVE = Component("knative")
ISTIO = Component("istio")
ISTIO_PROXY = Component("istio_proxy")
LINKERD = Component("linkerd")
LINKERD_VIZ = Component("linkerd_viz")
CALICO = Component("calico")
PROMETHEUS = Component("prometheus")

CLUSTER.components.extend(
    [
        KUBE_SYSTEM,
        CERT_MANAGER,
        NATS,
        KNATIVE,
        ISTIO,
        ISTIO_PROXY,
        LINKERD,
        LINKERD_VIZ,
        CALICO,
        PROMETHEUS,
    ]
)


### Functions ###
def signal_handler(signal, frame):
    LOADING_ANIMATION.stop_loading()
    log_info("\nScript interrupted")
    log_info("The script has been gracefully terminated")
    sys.exit(1)


def log(text, color=""):
    """
    Prints a line of text with an optional color formatting.

    Parameters:
        Required:
        - text (`str`): The text to be printed.

    Returns: `None`
    """

    print(color + text)


def log_info(text):
    """
    Prints a line of text with a yellow color formatting to indicate an information.

    Parameters:
        Required:
        - text (`str`): The text to be printed.

    Returns: `None`
    """

    log(text, YELLOW)


def log_error(text):
    """
    Prints a line of text with a red color formatting to indicate an error.

    Parameters:
        Required:
        - text (`str`): The text to be printed.

    Returns: `None`
    """

    log(text.rstrip("\n") + "\n", RED)


def log_success(text):
    """
    Prints a line of text with a green color formatting to indicate a success.

    Parameters:
        Required:
        - text (`str`): The text to be printed.

    Returns: `None`
    """

    log(text, GREEN)


def print_progress(text):
    """
    Prints a line of text with a yellow color formatting to indicate progress or status.

    Parameters:
        Required:
        - text (`str`): The text to be printed.

    Returns: `None`
    """

    sys.stdout.write("\r" + YELLOW + text)
    sys.stdout.flush()


def clear_console_line(text):
    """
    Clears a line of text displayed on the console output.

    Parameters:
        Required:
        - text (`str`): The line of text to be cleared.

    Returns: `None`
    """

    sys.stdout.write("\r" + " " * (len(text)) + "\r")
    sys.stdout.flush()


def input_color(prompt, color=""):
    """
    An input with an optional color formatting.

    Parameters:
        Required:
        - prompt (`str`): The text to be printed.

    Returns: `None`
    """

    if os.isatty(1) and color:  # 1 represents the file descriptor for standard output
        # ANSI escape codes are supported
        # Use colors in print statements
        input(color + prompt + END)
    else:
        # ANSI escape codes are not supported
        # Print without colors
        input(prompt)


def exit_script(reason, exit_code=1):
    """
    Terminate the script with an info reason and an exist code

    Parameters:
        Required:
        - reason (`str`): The exit reason that will be printed to the user.
        - exit_code (`str`): The exit code.

    Returns: `None`
    """

    LOADING_ANIMATION.stop_loading()
    log_info(reason)
    input_color("Press enter to exit...", YELLOW)
    sys.exit(exit_code)


def exit_script_on_error(reason, exit_code=1):
    """
    Terminate the script with an error reason and an exist code

    Parameters:
        Required:
        - reason (`str`): The exit reason that will be printed to the user.
        - exit_code (`str`): The exit code.

    Returns: `None`
    """

    LOADING_ANIMATION.stop_loading()
    log_error(reason)
    input_color("Press enter to exit...", RED)
    sys.exit(exit_code)


def try_cmd_error(cmd, error):
    """
    Returns info about the command that returned an error along with the error it returned.

    Parameters:
        Required:
        - cmd (`str`): The text to be printed.
        - error (`str`): The command error.

    Returns: `None`
    """

    return f"We tried to run the following command: `{cmd}` and it returned this error message: {error}"


def run_system_command(command, loading_description=""):
    """
    Run a command against the system and return the result.

    Parameters:
        Required:
        - command (`str`): The command to execute against the system.

        Optional:
        - loading_description (`str`): Specify a loading description to start loading on command execution.

    Returns:
        - output (`str`)
        - code (`int`)
        - error (`str`)
    """

    # Start loading if loading description is specified
    if loading_description:
        LOADING_ANIMATION.start_loading(loading_description)

    try:
        # Execute the command
        process = subprocess.Popen(
            command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )

        # Read the output and error streams
        output, error = process.communicate()

        # Stop loading if loading description is specified
        if loading_description:
            LOADING_ANIMATION.stop_loading()

        # Return the output
        return output.decode("utf-8"), process.returncode, error.decode("utf-8")
    except Exception as e:
        if loading_description:
            LOADING_ANIMATION.stop_loading()
        return "", -1, str(e).decode("utf-8")


def get_input(prompt, validate_func=None, default=""):
    """
    Reads a non-empty user input and returns it.
    Optionally provide a validation function and/or a default value for an empty input

    Parameters:
        Required:
        - prompt (`str`): The text to be displayed for the user before reading their input.

        Optional:
        - validate_fun (`function`): A function that takes the user input as a parameter and returns an error message if found.
            - Arguments:
                - user_input (`str`): The input of the user.
            - Return value:
                - An error message if found, an empty error message indicates that the validation was successful.

        - default (`str`): The default value to be returned on an empty user input.

    Returns: The user input as a string.
    """

    while True:
        # Read input from user
        user_input = input(prompt + " ")

        # Log an error if user input is empty or use default value
        if not user_input:
            # If the default has non empty value, use default
            if default:
                user_input = default
            else:
                log_error("Input cannot be empty, please try again")
                continue

        # Perform input validation if `validate_func` is defined
        validation_message = (
            validate_func(user_input) if validate_func and user_input else ""
        )

        # Log the error if the error message is not empty
        if validation_message:
            log_error(validation_message)
            continue

        return user_input


def get_user_confirmation(prompt, option1="y", option2="n"):
    """
    Reads an expected user input and returns a boolean
    indicating if the first option was submitted.

    Parameters:
        Required:
        - prompt (`str`): The text to be displayed for the user before reading their input.

        Optional:
        - option1 (`str`): The first option to expect.
        - option2 (`str`): The second option to expect.

    Returns: `True` if the user input matches the first option and `False` if it doesn't.

    """

    while True:
        option1 = option1.lower()
        option2 = option2.lower()
        response = input(prompt + " ").strip().lower()

        if response == option1 or response == option2:
            return response == option1

        log_error(f"Invalid input. Please enter '{option1}' or '{option2}'")


def is_kubectl_missing():
    """
    Check if `kubectl` command is available on the target machine.

    Returns: `True` if the (kubectl) command is found and `False` if otherwise.

    """

    try:
        if platform.system() == "Windows":
            subprocess.check_output(["where", "kubectl"])
        else:
            subprocess.check_output(["which", "kubectl"])
        return False
    except subprocess.CalledProcessError:
        return True


def extract_value_from_unit(value):
    """
    Separates a number from a string and returns the number.

    Parameters:
        - value (`any`): The value to separate the number from.

    Returns: The extract number as a `float`.
    """

    # Check if the field is a numeric value without a unit
    if re.match(r"^\d+$", value):
        result = value  # Assume the value is already a number
    else:
        # Extract value and unit using the regular expression pattern
        try:
            result, _ = re.match(r"^(\d+)([A-Za-z]+)$", value).groups()
        except Exception as e:
            # If the expression above threw an exception then the value is unknown
            result = 0.0

    return float(result)


def validate_email(email):
    """
    Validates an email and returns an error message if it is invalid.

    Parameters:
        - email (`str`): The email to validate.

    Returns: The error message as a string.
    """

    pattern = r"^[\w\.-]+@[\w\.-]+\.\w+$"
    errorMessage = ""

    if re.match(pattern, email) is None:
        errorMessage = "Email is invalid, please try again"

    return errorMessage


def validate_number(input):
    """
    Validates whether the provided string is a number or not.

    Parameters:
        - input (`str`): The string to validate.

    Returns: The error message as a string.
    """

    pattern = r"^[-+]?(\d+(\.\d*)?|\.\d+)([eE][-+]?\d+)?$"
    errorMessage = ""

    if re.match(pattern, input) is None:
        errorMessage = "Invalid input, please enter a valid number"

    return errorMessage


def custom_round(number):
    """
    The `custom_round` function takes a single float as input and returns the nearest integer value.
    If the decimal part of the number is greater than or equal to 0.2, it will round up to the next integer.
    If the decimal part of the number is less than 0.2, it will round down to the nearest integer.
    This is achieved by adding 0.3 to the input number and then using the built-in `round()` function in Python.
    For example, if the input is 8.81899614313, the function will return 9.
    If the input is 8.2, the function will return 8.

    Parameters:
        - number (`float`): The number to perform the round on.

    Returns the result
    """

    return round(number + 0.3)


def serialize_object(obj):
    """
    Convert class instance to a dictionary

    Parameters:
        - obj (`object`): The object to convert to a dictionary.

    returns the object as a dictionary.
    """
    return obj.__dict__


def is_output_available(pipe, timeout=0.1):
    """
    Check if there is any output available on a file object.

    Parameters:
        - pip (`io.TextIOWrapper`): File object to check for output.
        - timeout (`float`): Maximum time to wait for output in seconds. Default is 0.1 seconds.

    Returns:
        True if there is any output available, False otherwise.
    """

    try:
        return bool(select.select([pipe], [], [], timeout)[0])
    except Exception as _:
        return False


def get_nested_value(keys_array, nested_dict, default_value):
    """
    Safely retrieves a nested value from a dictionary based on the provided keys array.

    Parameters:
        - keys_array (`list`): A list of strings representing the sequence of nested keys.
        - nested_dict (`dict`): The dictionary from which the nested value will be retrieved.
        - default_value: The default value to be returned if any key is missing or the nesting structure is invalid..

    Returns:
        The nested value from the dictionary if all keys are valid and the nesting structure is correct.
        If any key is missing or the nesting structure is invalid, it returns the default_value
        (or None if not specified).
    """

    try:
        for key in keys_array:
            nested_dict = nested_dict[key]
        return nested_dict
    except (KeyError, TypeError):
        return default_value


def get_top_nodes():
    """
    Safely retrieves nodes usage consumption through 'metrics-server'

    Returns:
        The `kubectl top node` output and the error message if found

    """

    error_message = None
    cmd = "kubectl top node"
    output, cmd_code, cmd_err = run_system_command(
        cmd, "Checking if metrics-server is available"
    )

    if cmd_code == 1:
        cmd_err = f"{cmd_err}\nPerhaps your kubeconfig isn’t pointing to a healthy cluster, or your K8s metrics API isn’t available. Please check your K8s cluster, and try again. Email support@controlplane.com and we’ll be happy to help troubleshoot with you"

    if cmd_code != 0:
        error_message = try_cmd_error(cmd, cmd_err)

    if len(output.strip().split("\n")) < 2:
        error_message = f"`{cmd}` command returned an empty list, make sure you have nodes running in your cluster"

    return output, error_message


def get_top_level_controller_in_memory(namespace, pod_name, depth=5):
    """
    Recursively trace a Pod's ownerReferences up to a maximum depth (default=5).
    Returns (top_kind, top_name). If there are no more owners or we exceed the depth,
    it returns ("Pod", pod_name).

    Args:
        namespace (str): The namespace of the Pod.
        pod_name (str): The name of the Pod.
        depth (int): The maximum recursion depth. Defaults to 5.

    Returns:
        (str, str): A tuple containing the final top-level controller kind and name.
    """
    # Prevent infinite recursion by limiting depth
    if depth <= 0:
        return ("Pod", pod_name)

    # Search for the matching Pod object in pods_all_json
    key_pod = None
    for item in pods_all_json["items"]:
        if item["metadata"]["name"] == pod_name and item["metadata"]["namespace"] == namespace:
            key_pod = item
            break

    # If the Pod doesn't exist in pods_all_json, treat it as top-level
    if not key_pod:
        return ("Pod", pod_name)

    # Get the Pod's ownerReferences (list of owners)
    owners = key_pod["metadata"].get("ownerReferences", [])

    # If no owners, it's top-level
    if not owners:
        return ("Pod", pod_name)

    # Look for the main controller, if any
    primary_owner = next((ref for ref in owners if ref.get("controller", False)), None)
    if not primary_owner:
        primary_owner = owners[0]

    # Get the kind and name of the primary owner
    owner_kind = primary_owner.get("kind")
    owner_name = primary_owner.get("name")

    # Consider certain kinds (Deployment, StatefulSet, DaemonSet) immediately top-level
    if owner_kind in ["Deployment", "StatefulSet", "DaemonSet"]:
        return (owner_kind, owner_name)

    # If it's a Job, check if it's owned by a CronJob.
    elif owner_kind == "Job":
        job_item = jobs_dict.get((namespace, owner_name))
        if not job_item:
            return ("Job", owner_name)
        job_owners = job_item["metadata"].get("ownerReferences", [])
        if not job_owners:
            return ("Job", owner_name)
        job_primary = next((r for r in job_owners if r.get("controller", False)), job_owners[0])
        if job_primary["kind"] == "CronJob":
            return ("CronJob", job_primary["name"])
        return (job_primary["kind"], job_primary["name"])

    # CronJob is typically considered top-level.
    elif owner_kind == "CronJob":
        return (owner_kind, owner_name)

    # If it's a ReplicaSet, we may find a higher-level Deployment, etc.
    if owner_kind == "ReplicaSet":
        rs_item = replicaset_dict.get((namespace, owner_name))
        if not rs_item:
            return (owner_kind, owner_name)
        rs_owners = rs_item["metadata"].get("ownerReferences", [])
        if not rs_owners:
            return (owner_kind, owner_name)
        rs_primary = next((r for r in rs_owners if r.get("controller", False)), None)
        if not rs_primary:
            rs_primary = rs_owners[0]
        if rs_primary["kind"] in ["Deployment", "StatefulSet", "DaemonSet", "Job", "CronJob"]:
            return (rs_primary["kind"], rs_primary["name"])
        
        # Otherwise, keep climbing up one more level.
        return get_top_level_controller_in_memory(namespace, owner_name, depth - 1)

    # If it's something else unknown, treat the current resource as top-level.
    return (owner_kind, owner_name)


def get_prometheus_servers():
    """
    Safely retrieves prometheus servers that are available in the cluster

    Returns:
        A list of KubernetesService object
    """

    cmd = "kubectl get services -A"
    output, cmd_code, cmd_err = run_system_command(
        cmd, "Checking if prometheus is available in the cluster"
    )

    if cmd_code != 0 or cmd_err or not output or len(output.strip().split("\n")) < 2:
        return None

    prometheus_servers = []
    services_lines = output.strip().split("\n")

    for service_line in services_lines[1:]:
        fields = service_line.split()

        service_namespace = fields[SERVICES_TABLE_COLUMNS[SERVICE_NAMESPACE_COLUMN]]
        service_name = fields[SERVICES_TABLE_COLUMNS[SERVICE_NAME_COLUMN]]
        service_port = extract_first_port(
            fields[SERVICES_TABLE_COLUMNS[SERVICE_PORTS_COLUMN]]
        )

        if "prometheus-server" not in service_name:
            continue

        if not service_port:
            log_info(
                f"WARNING: Skipping the prometheus service with the name '{service_name}' because it does not have a single port to forward to"
            )
            continue

        # If a service name contains the word 'prometheus-server' then a prometheus server was found
        prometheus_servers.append(
            KubernetesService(service_namespace, service_name, service_port)
        )

    return prometheus_servers


def extract_first_port(ports_string):
    """
    Extracts the first port number from a ports string

    Parameters:
        - ports_string (`str`): The string the contains ports separated with a comma

    Returns:
        The first port number found in the `ports_string`
    """

    if not ports_string:
        return None

    # Split the string at the comma (for cases like "80/TCP,443/TCP")
    if "," in ports_string:
        ports_string = ports_string.split(",")[0]

    # Split again at the "/" and take the first part to get the port number
    if "/" in ports_string:
        ports_string = ports_string.split("/")[0]

    if ":" in ports_string:
        return None

    return ports_string


def run_port_forward(namespace, service_name, target_port):
    """
    Port-forward a Kubernetes service to available local ports, starting from 3010.
    It tries up to 30 ports incrementing by 1 each time.

    Parameters:
        - namespace (`str`): The Kubernetes namespace where the service resides.
        - service_name (`str`): The name of the service to port-forward.
        - target_port (`int`): The port on the service to forward.

    Returns:
        A reference to the process instance
    """

    # None, False and empty until proven otherwise
    process = None
    local_port = None
    is_success = False
    error_messages = []

    LOADING_ANIMATION.start_loading(
        f"Attempting to port-forward to service/{service_name}"
    )

    # Give the port forward command a few chances to work before returning error
    for index in range(FIND_PORT_MAX_TRIES):
        if is_success:
            break

        current_iteration = 0
        local_port = random.randint(LOCAL_PORT_START, LOCAL_PORT_END)

        try:
            cmd = f"kubectl port-forward service/{service_name} {local_port}:{target_port} -n {namespace}"
            process = subprocess.Popen(
                cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE
            )

            while not is_success:
                if MAX_CHECK_FOR_SUCCESS_ATTEMPTS == current_iteration:
                    process.terminate()
                    break

                # Read line from stdout and stderr
                process_output = process.stdout
                process_error = process.stderr

                if process_error and is_output_available(process_error):
                    error_decoded = process_error.readline().strip().decode()

                    if error_decoded:
                        process.terminate()
                        error_messages.append(error_decoded)
                        break

                if process_output and is_output_available(process_output):
                    output_decoded = process_output.readline().strip().decode()

                    if (
                        "Forwarding from" in output_decoded
                        and str(local_port) in output_decoded
                    ):
                        is_success = True
                        break

                time.sleep(CHECK_FOR_SUCCESS_TIME_TO_WAIT_BEFORE_RETRY)
                current_iteration += 1

        except Exception as e:
            process.terminate()
            error_messages.append(f"Exception Error: {str(e)}")

    # Handle port forward errors
    if not process or not local_port or not is_success:
        if process:
            process.terminate()

        exit_error_message = f"Failed to port-forward service/{service_name} -n {namespace} after {FIND_PORT_MAX_TRIES} attempts.\n"

        if error_messages:
            exit_error_message += "\nThe following is a list of errors we encountered in the following attempts:\n"

        for index, message in enumerate(error_messages):
            exit_error_message += f"Attempt {index + 1}: {message}\n"

        exit_script_on_error(exit_error_message)

    LOADING_ANIMATION.stop_loading()

    return process, local_port


def perform_prometheus_query(query, port):
    """
    Make a request to the prometheus server running in an open port.

    Parameters:
        - query (`str`): The prometheus query to perform.
        - port (`int`): The port number of the port forwarded prometheus server

    Returns:
        The content of the request and whether the request was a success
    """

    try:
        endpoint = f"http://localhost:{port}/api/v1/query?query={query}"
        response = requests.get(endpoint)

        if response.status_code != 200:
            return response.content.decode("utf-8"), False

        return response.json(), True
    except Exception as e:
        return str(e), False


def get_prometheus_request_error(request_error_message, additional_message):
    """
    Generate a prometheus specific error message to show to the user.

    Parameters:
        - additional_message (`str`): The message to base the error message on.

    Returns the error message
    """

    return f"An error has occurred while trying to make a request to the Prometheus server, this is the content of the error:\n\n{request_error_message}\n\nWe were not able to get {additional_message} through the prometheus server, please try again or consider having metrics server set up in your cluster and choose it as the metric collection method when you run the K8s Cost Analyzer again."


def process_prometheus_query(message, query, local_port, process):
    """
    Perform and process a prometheus query.

    Parameters:
        - message (`str`): The message to complete the error message.
        - query (`str`): The query to perform against Prometheus.
        - local_port (`int`): The forwarded port to the Prometheus server.
        - process (`Popen[bytes] | None`): The reference to the process that
            has forwarded a port to a Prometheus server.

    Returns the result object that returned from the query output.
    """
    LOADING_ANIMATION.start_loading(f"Getting {message}")
    query_result_json, is_success = perform_prometheus_query(query, local_port)
    LOADING_ANIMATION.stop_loading()

    # Handle request error
    if not is_success:
        process.terminate()
        exit_script_on_error(
            get_prometheus_request_error(
                query_result_json,
                message,
            )
        )

    return get_nested_value(["data", "result"], query_result_json, "")


def process_nodes_prometheus_query(
    message,
    query,
    local_port,
    process,
):
    """
    Perform and process a prometheus query for nodes.

    Parameters:
        - message (`str`): The message to complete the error message.
        - query (`str`): The query to perform against Prometheus.
        - local_port (`int`): The forwarded port to the Prometheus server.
        - process (`Popen[bytes] | None`): The reference to the process that
            has forwarded a port to a Prometheus server.

    Returns a node name to metric value dictionary.
    """
    node_name_to_value = {}
    data_result = process_prometheus_query(message, query, local_port, process)

    for _, item in enumerate(data_result):
        node_name = get_nested_value(["metric", "kubernetes_node_name"], item, None)
        item_value = get_nested_value(["value"], item, [])

        if not node_name or not item_value:
            continue

        # Get last element and set it as the CPU usage consumption
        node_name_to_value[node_name] = custom_round(float(item_value[-1]))

    return node_name_to_value


def process_pods_prometheus_query(
    message,
    query,
    local_port,
    process,
):
    """
    Perform and process a prometheus query for pods.

    Parameters:
        - message (`str`): The message to complete the error message.
        - query (`str`): The query to perform against Prometheus.
        - local_port (`int`): The forwarded port to the Prometheus server.
        - process (`Popen[bytes] | None`): The reference to the process that
            has forwarded a port to a Prometheus server.

    Returns a namespace&pod_name&container_name to metric value dictionary.
    """

    pod_namespace_to_pod_data = {}
    data_result = process_prometheus_query(message, query, local_port, process)

    for _, item in enumerate(data_result):
        pod_namespace = get_nested_value(["metric", "namespace"], item, None)
        pod_name = get_nested_value(["metric", "pod"], item, None)
        pod_container = get_nested_value(["metric", "container"], item, None)
        item_value = get_nested_value(["value"], item, [])

        if not pod_namespace or not pod_name or not pod_container or not item_value:
            continue

        dict_key = f"{pod_namespace}&{pod_name}&{pod_container}"

        if dict_key not in pod_namespace_to_pod_data:
            pod_namespace_to_pod_data[dict_key] = 0.0

        pod_namespace_to_pod_data[dict_key] += custom_round(float(item_value[-1]))

    return pod_namespace_to_pod_data


def submit_cluster(submission):
    """
    Submit cluster data to the backend service

    Parameters:
        - submission (`Submission`): An instance of the Submission class.

    Returns: `None`
    """

    try:
        submission_json = json.dumps(submission, default=serialize_object)
        headers = {"Content-Type": "application/json"}

        LOADING_ANIMATION.start_loading("Submitting the cluster info to the backend")
        http_response = requests.post(ENDPOINT, headers=headers, data=submission_json)
        LOADING_ANIMATION.stop_loading()

        # Check if the backend service was unable to figure out the prices for some nodes
        if http_response.status_code == 422:
            unpriced_nodes = http_response.json()["message"]

            # Prompt the user to enter the price for each failed node
            for unpriced_node in unpriced_nodes:
                explicit_price = float(
                    get_input(
                        f"Machine type cost unknown. Please provide the monthly cost for '{unpriced_node['instance_type']}' region '{unpriced_node['region']}':",
                        validate_number,
                    )
                )

                # Update the cluster data
                for node in submission.cluster.nodes:
                    if (
                        node.instance_type == unpriced_node["instance_type"]
                        and node.region == unpriced_node["region"]
                    ):
                        node.explicit_price = explicit_price

            # Retry request
            submit_cluster(submission)
            return

        # For any other fail reason, exit with an error
        if http_response.status_code < 200 or http_response.status_code > 299:
            exit_script_on_error(http_response.content.decode("utf-8"))

        log_success("The script has executed successfully!")
        log_success(f"Here is the link to your result: {http_response.json()}")

    except Exception as e:
        exit_script_on_error(
            f"We encountered an issue with the request, please contact the Control Plane team and share this error message: {str(e)}"
        )


### Handle Arguments ###
if len(sys.argv) > 1 and sys.argv[1] == "--version":
    print("v1.1.2")
    sys.exit(0)

### START ###
colorama.init(autoreset=True)
LOADING_ANIMATION.start_loading("Starting K8s Cost Analyzer, please wait")
os.environ["SSL_CERT_FILE"] = certifi.where()
signal.signal(signal.SIGINT, signal_handler)

if sys.version_info.major != 3:
    exit_script_on_error("This script requires Python 3.x or higher")

if is_kubectl_missing():
    exit_script_on_error(
        "kubectl CLI is not found on this platform, make sure you have kubectl CLI installed and set up before running the script again"
    )
LOADING_ANIMATION.stop_loading()

log("\n*** Control Plane - K8s Cost Analyzer ***\n", BLUE)
log_info(
    "This script gathers detailed resource consumption data of a K8s cluster in a read-only manner"
)
log_info(
    "After successful execution, a link to the result will be printed in the terminal.\n"
)

# STEP 1 - Retrieve user input
user_name = get_input("Enter your name:")
user_email = get_input(
    "Enter your email (the result will also be emailed to you):", validate_email
)

# STEP 2 - Determine the metric collection method
has_metrics_server = False
has_prometheus = False
should_use_prometheus = False
should_use_metrics_server = False

# Attempt to get nodes' usage consumption through 'metrics-server'
top_nodes_output, top_nodes_error_message = get_top_nodes()

# !! Prometheus will be supported in a later phase, it will be on hold for now as it is not complete
# Attempt to get prometheus servers
# prometheus_servers_collection = get_prometheus_servers()
prometheus_servers_collection = []

# If the metrics server did not return an error, then metrics collection through `metrics-server` is valid
if not top_nodes_error_message:
    has_metrics_server = True

# If the prometheus servers collection is not empty, then metrics collection through `prometheus` is valid
if prometheus_servers_collection:
    has_prometheus = True

# If both metrics collection methods are not available, exit and return an error
if not has_metrics_server and not has_prometheus:
    exit_script_on_error(top_nodes_error_message)

# If prometheus is available and metrics server is not, use prometheus
if not has_metrics_server and has_prometheus:
    should_use_prometheus = True

# If metrics server is available and prometheus is not, use metrics server
elif has_metrics_server and not has_prometheus:
    should_use_metrics_server = True

# If both metrics collection methods are available, ask the user what metric collection they prefer the script to use
elif has_metrics_server and has_prometheus:
    should_use_prometheus = get_user_confirmation(
        "We noticed that your cluster is using Prometheus and metrics server to collect metrics, would you like the script to use metrics server or use Prometheus? (prometheus/metrics-server)",
        "prometheus",
        "metrics-server",
    )

# STEP 3 - Start collecting metrics
# Get nodes as objects through JSON
cmd = "kubectl get nodes -o json"
nodes_json_output, cmd_code, cmd_err = run_system_command(
    cmd, "Collecting info of all nodes in the cluster, please wait"
)

if cmd_code != 0:
    exit_script_on_error(try_cmd_error(cmd, cmd_err))

# Collect nodes info and create new node instances
nodes_json = json.loads(nodes_json_output)
if "items" not in nodes_json:
    exit_script_on_error("Error: we were unable to find nodes in your cluster")

if should_use_prometheus:
    log_info(
        "[INFO] Prometheus will be used to calculate resources consumption with a period of 48 hours"
    )
    log_info(
        f"[INFO] We will go over {len(prometheus_servers_collection)} prometheus server{'s' if len(prometheus_servers_collection) > 1 else ''} in the cluster and fetch metrics."
    )

    # Set available node names
    available_node_names = []

    for index, node_json in enumerate(nodes_json["items"]):
        node_name = get_nested_value(["metadata", "name"], node_json, None)
        available_node_names.append(node_name)

    # Port forward each prometheus server and collect metrics
    for prometheus_server in prometheus_servers_collection:
        log_info(
            f"[INFO] Currently collecting metrics through the prometheus server: '{prometheus_server.name}'\n"
        )

        prometheus_server_process, local_port = run_port_forward(
            prometheus_server.namespace, prometheus_server.name, prometheus_server.port
        )

        # Get pods' usage consumption through Prometheus server
        pods_cpu_usage_dict = process_pods_prometheus_query(
            "pods' cpu usage consumption",
            PODS_TOTAL_CPU_USAGE_QUERY,
            local_port,
            prometheus_server_process,
        )
        pods_memory_usage_dict = process_pods_prometheus_query(
            "pods' memory usage consumption",
            PODS_TOTAL_MEMORY_USAGE_QUERY,
            local_port,
            prometheus_server_process,
        )

        for key, value in pods_cpu_usage_dict.items():
            # Skip container if no memory usage consumption was found for it
            if key not in pods_memory_usage_dict:
                continue

            namespace, pod_name, container = key.split("&")

            cpu_usage = value
            memory_usage = pods_memory_usage_dict[key]

            PODS_USAGE_CONSUMPTION_LIST.append(
                PodUsageConsumption(
                    pod_name, namespace, container, cpu_usage, memory_usage
                )
            )

        # Get nodes' usage consumption through Prometheus server
        nodes_cpu_usage_dict = process_nodes_prometheus_query(
            "nodes' CPU usage consumption",
            NODES_TOTAL_CPU_USAGE_QUERY,
            local_port,
            prometheus_server_process,
        )
        nodes_memory_usage_dict = process_nodes_prometheus_query(
            "nodes' memory usage consumption",
            NODES_TOTAL_MEMORY_USAGE_QUERY,
            local_port,
            prometheus_server_process,
        )
        nodes_cpu_used_percentage_dict = process_nodes_prometheus_query(
            "nodes' CPU usage percentage",
            NODES_TOTAL_CPU_USED_PERCENTAGE_QUERY,
            local_port,
            prometheus_server_process,
        )
        nodes_memory_used_percentage_dict = process_nodes_prometheus_query(
            "nodes' memory usage percentage",
            NODES_TOTAL_MEMORY_USED_PERCENTAGE_QUERY,
            local_port,
            prometheus_server_process,
        )

        # Create NodeUsageConsumption objects
        for node_name in available_node_names:
            if (
                node_name not in nodes_cpu_usage_dict
                or node_name not in nodes_memory_usage_dict
                or node_name not in nodes_cpu_used_percentage_dict
                or node_name not in nodes_memory_used_percentage_dict
            ):
                continue

            NODES_USAGE_CONSUMPTION_DICT[node_name] = NodeUsageConsumption(
                nodes_cpu_usage_dict[node_name],
                nodes_memory_usage_dict[node_name],
                nodes_cpu_used_percentage_dict[node_name],
                nodes_memory_used_percentage_dict[node_name],
            )

        prometheus_server_process.terminate()

    # Check if the PODS_USAGE_CONSUMPTION_LIST is not empty, and if it is empty, return an error to the user
    if not PODS_USAGE_CONSUMPTION_LIST:
        message = "We were unable to get pods usage consumption through Prometheus due to an empty result or missing labels from the queries we executed against the Prometehus servers in the cluster.\n\nFeel free to email support@controlplane.com and we’ll be happy to help troubleshoot with you."

        if has_metrics_server:
            log_error(message)

            should_use_metrics_server = get_user_confirmation(
                "\nSince metrics server is already set up on the cluster, would you like the script to use metrics server for metric collection instead?",
                "y",
                "n",
            )

        else:
            exit_script_on_error(message)


if should_use_metrics_server:
    log_info(
        "[INFO] `kubectl top` command will be used to calculate resources consumption\n"
    )

    cmd = "kubectl top pod -A --containers=true"
    top_pods_output, cmd_code, cmd_err = run_system_command(
        cmd, "Collecting usage consumption of all running pods"
    )

    if cmd_code != 0 or cmd_err:
        exit_script_on_error(try_cmd_error(cmd, cmd_err))

    if not top_pods_output or len(top_pods_output.strip().split("\n")) < 2:
        exit_script_on_error(
            f"`{cmd}` command returned an empty list, make sure you have pods running in your cluster"
        )

    top_pods_lines = top_pods_output.strip().split("\n")

    # Iterate over pods and collect cpu and memory usage
    for top_pod in top_pods_lines[1:]:  # Start from second line and skip header
        fields = top_pod.split()  # Split line into fields
        isComponent = True  # The value is True until proven False

        pod_namespace = fields[TOP_PODS_TABLE_COLUMNS[POD_NAMESPACE_COLUMN]]
        pod_name = fields[TOP_PODS_TABLE_COLUMNS[POD_NAME_COLUMN]]
        pod_container_name = fields[TOP_PODS_TABLE_COLUMNS[POD_CONTAINER_NAME_COLUMN]]
        pod_cpu = extract_value_from_unit(
            fields[TOP_PODS_TABLE_COLUMNS[POD_CPU_COLUMN]]
        )
        pod_memory = extract_value_from_unit(
            fields[TOP_PODS_TABLE_COLUMNS[POD_MEMORY_COLUMN]]
        )

        PODS_USAGE_CONSUMPTION_LIST.append(
            PodUsageConsumption(
                pod_name, pod_namespace, pod_container_name, pod_cpu, pod_memory
            )
        )

    # Map nodes names to their usage consumption
    top_nodes_lines = top_nodes_output.strip().split("\n")

    for top_node in top_nodes_lines[1:]:
        fields = top_node.split()

        node_name = fields[TOP_NODES_TABLE_COLUMNS[NODE_NAME_COLUMN]]
        node_cpu = (
            extract_value_from_unit(fields[TOP_NODES_TABLE_COLUMNS[NODE_CPU_COLUMN]])
            / 1000
        )
        node_memory = extract_value_from_unit(
            fields[TOP_NODES_TABLE_COLUMNS[NODE_MEMORY_COLUMN]]
        )
        node_requests_cpu = fields[TOP_NODES_TABLE_COLUMNS[NODE_REQUESTS_CPU_COLUMN]]
        node_requests_memory = fields[
            TOP_NODES_TABLE_COLUMNS[NODE_REQUESTS_MEMORY_COLUMN]
        ]

        NODES_USAGE_CONSUMPTION_DICT[node_name] = NodeUsageConsumption(
            node_cpu, node_memory, node_requests_cpu, node_requests_memory
        )


# STEP 4 - Get cluster name & kubernetes version
cmd = "kubectl config current-context"
current_context_output, cmd_code, cmd_err = run_system_command(
    cmd, "Getting cluster name"
)

if cmd_code != 0:
    exit_script_on_error(try_cmd_error(cmd, cmd_err))

cmd = "kubectl version -o json"
kubernetes_version_json, cmd_code, cmd_err = run_system_command(
    cmd, "Getting kubernetes version"
)

if cmd_code != 0:
    exit_script_on_error(try_cmd_error(cmd, cmd_err))

try:
    kubernetes_version_dict = json.loads(kubernetes_version_json)

    CLUSTER.name = current_context_output
    CLUSTER.kubernetes_version = kubernetes_version_dict["serverVersion"]["gitVersion"]

except Exception as e:
    exit_script_on_error(
        f"ERROR: we were unable to get Kubernetes version. Exception: {str(e)}"
    )

# STEP 5 - Process pods
cmd = "kubectl get pods -A -o json"
pods_all_json_str, cmd_code, cmd_err = run_system_command(cmd, "Collecting all Pods as JSON")
if cmd_code != 0 or not pods_all_json_str:
    exit_script_on_error(try_cmd_error(cmd, cmd_err))
pods_all_json = json.loads(pods_all_json_str)

cmd = "kubectl get replicasets -A -o json"
replicasets_json_str, cmd_code, cmd_err = run_system_command(cmd, "Collecting all ReplicaSets as JSON")
if cmd_code != 0 or not replicasets_json_str:
    exit_script_on_error(try_cmd_error(cmd, cmd_err))
replicasets_json = json.loads(replicasets_json_str)

cmd = "kubectl get deployments -A -o json"
deployments_json_str, cmd_code, cmd_err = run_system_command(cmd, "Collecting all Deployments as JSON")
if cmd_code != 0 or not deployments_json_str:
    exit_script_on_error(try_cmd_error(cmd, cmd_err))
deployments_json = json.loads(deployments_json_str)

cmd = "kubectl get statefulsets -A -o json"
statefulsets_json_str, cmd_code, cmd_err = run_system_command(cmd, "Collecting all StatefulSets as JSON")
statefulsets_json = json.loads(statefulsets_json_str)

cmd = "kubectl get daemonsets -A -o json"
daemonsets_json_str, cmd_code, cmd_err = run_system_command(cmd, "Collecting all DaemonSets as JSON")
daemonsets_json = json.loads(daemonsets_json_str)

cmd = "kubectl get jobs -A -o json"
jobs_json_str, cmd_code, cmd_err = run_system_command(cmd, "Collecting all Jobs as JSON")
jobs_json = json.loads(jobs_json_str)

cmd = "kubectl get cronjobs -A -o json"
cronjobs_json_str, cmd_code, cmd_err = run_system_command(cmd, "Collecting all CronJobs as JSON")
cronjobs_json = json.loads(cronjobs_json_str)

# Build dictionaries for quick lookups
replicaset_dict = {}
for rs_item in replicasets_json.get("items", []):
    rs_ns = rs_item["metadata"]["namespace"]
    rs_name = rs_item["metadata"]["name"]
    replicaset_dict[(rs_ns, rs_name)] = rs_item

deployment_dict = {}
for dep_item in deployments_json.get("items", []):
    dep_ns = dep_item["metadata"]["namespace"]
    dep_name = dep_item["metadata"]["name"]
    deployment_dict[(dep_ns, dep_name)] = dep_item

statefulset_dict = {}
for sts_item in statefulsets_json.get("items", []):
    sts_ns = sts_item["metadata"]["namespace"]
    sts_name = sts_item["metadata"]["name"]
    statefulset_dict[(sts_ns, sts_name)] = sts_item

daemonset_dict = {}
for ds_item in daemonsets_json.get("items", []):
    ds_ns = ds_item["metadata"]["namespace"]
    ds_name = ds_item["metadata"]["name"]
    daemonset_dict[(ds_ns, ds_name)] = ds_item

jobs_dict = {}
for job_item in jobs_json.get("items", []):
    job_ns = job_item["metadata"]["namespace"]
    job_name = job_item["metadata"]["name"]
    jobs_dict[(job_ns, job_name)] = job_item

cronjobs_dict = {}
for cj_item in cronjobs_json.get("items", []):
    cj_ns = cj_item["metadata"]["namespace"]
    cj_name = cj_item["metadata"]["name"]
    cronjobs_dict[(cj_ns, cj_name)] = cj_item

applications_dict = {}
pod_name_to_node_name = {}
namespace_to_pod_mapping = {}

# Also get full pod info from this new JSON to map the node & labels
for pod_item in pods_all_json.get("items", []):
    pod_namespace = pod_item["metadata"]["namespace"]
    pod_name = pod_item["metadata"]["name"]
    pod_labels = pod_item["metadata"].get("labels", {})
    pod_node_name = get_nested_value(["spec","nodeName"], pod_item, "")

    if pod_namespace not in namespace_to_pod_mapping:
        namespace_to_pod_mapping[pod_namespace] = {}

    pod_name_to_node_name[pod_name] = pod_node_name
    namespace_to_pod_mapping[pod_namespace][pod_name] = pod_labels

# Iterate over pods and collect cpu and memory usage
for pod in PODS_USAGE_CONSUMPTION_LIST:
    isComponent = True  # The value is True until proven False

    pod_node_name = ""
    pod_has_labels = (
        # Check if namespace key exists
        pod.namespace in namespace_to_pod_mapping
        # Check if pod name key exists
        and pod.name in namespace_to_pod_mapping[pod.namespace]
        # Check if labels are not empty
        and namespace_to_pod_mapping[pod.namespace][pod.name]
    )

    if pod.name in pod_name_to_node_name:
        pod_node_name = pod_name_to_node_name[pod.name]

    if "kube-system" == pod.namespace:
        KUBE_SYSTEM.add_usage(pod.cpu, pod.memory)
    elif "cert-manager" == pod.namespace:
        CERT_MANAGER.add_usage(pod.cpu, pod.memory)
    elif "nats" in pod.namespace:
        NATS.add_usage(pod.cpu, pod.memory)
    elif "knative" in pod.namespace:
        KNATIVE.add_usage(pod.cpu, pod.memory)
    elif "calico" in pod.namespace or "calico" in pod.name:
        CALICO.add_usage(pod.cpu, pod.memory)
    elif "istio" in pod.namespace or "istiod" in pod.name:
        ISTIO.add_usage(pod.cpu, pod.memory)
    elif "istio-proxy" in pod.container:
        ISTIO_PROXY.add_usage(pod.cpu, pod.memory)
    elif "linkerd-proxy" in pod.container:
        LINKERD.add_usage(pod.cpu, pod.memory)
    elif (
        "prometheus" in pod.namespace
        or "prometheus" in pod.name
        or "prometheus" in pod.container
    ):
        PROMETHEUS.add_usage(pod.cpu, pod.memory)
    elif pod_has_labels:
        pod_labels = namespace_to_pod_mapping[pod.namespace][pod.name]
        if "app.kubernetes.io/name=knative-operator" in pod_labels:
            KNATIVE.add_usage(pod.cpu, pod.memory)
        elif "linkerd.io/control-plane-component" in pod_labels:
            LINKERD.add_usage(pod.cpu, pod.memory)
        elif "linkerd.io/extension=viz" in pod_labels:
            LINKERD_VIZ.add_usage(pod.cpu, pod.memory)
        elif "tigera-operator" in pod_labels:
            CALICO.add_usage(pod.cpu, pod.memory)
        else:
            isComponent = False
    else:
        isComponent = False

    # If the pod is not a component then it is an application
    if not isComponent:
        # Get the top level controller kind and name of the pod
        top_kind, top_name = get_top_level_controller_in_memory(pod.namespace, pod.name, depth=5)

        # e.g. "Deployment/my-app"
        top_level_id = f"{pod.namespace}/{top_kind}/{top_name}"

        # Initialize a new application if it does not exist
        if top_level_id not in applications_dict:
            # Create a new application
            new_application = Application(top_level_id, pod_node_name)

            # Map the application id to the applications dictionary
            applications_dict[top_level_id] = new_application

            # Add the application to the cluster
            CLUSTER.applications.append(new_application)

        # Add the pod's usage to the application
        applications_dict[top_level_id].cpu_usage += pod.cpu
        applications_dict[top_level_id].memory_usage += pod.memory

    CLUSTER.total_usage_cpu += pod.cpu
    CLUSTER.total_usage_memory += pod.memory

# STEP 6 - Process nodes
nodes_sharing_type = {}

for index, node_json in enumerate(nodes_json["items"]):
    new_node = Node()

    new_node.name = get_nested_value(["metadata", "name"], node_json, "unknown")
    new_node.capacity_cpu = extract_value_from_unit(
        get_nested_value(["status", "capacity", "cpu"], node_json, 0.0)
    )
    new_node.capacity_memory = (
        extract_value_from_unit(
            get_nested_value(["status", "capacity", "memory"], node_json, 0.0)
        )
        / 1024
    )
    new_node.allocatable_cpu = (
        extract_value_from_unit(
            get_nested_value(["status", "allocatable", "cpu"], node_json, 0.0)
        )
        / 1000
    )
    new_node.allocatable_memory = (
        extract_value_from_unit(
            get_nested_value(["status", "allocatable", "memory"], node_json, 0.0)
        )
        / 1024
    )
    new_node.cloud_provider = get_nested_value(
        ["spec", "providerID"], node_json, CLOUD_PROVIDER_UNKNOWN
    )

    node_labels = get_nested_value(["metadata", "labels"], node_json, None)

    # Assume the node has a cloud provider now, determine later
    node_has_cloud_provider = True
    cost_request_message = f"this node with the name `{node_name}`"

    # Get node's consumbed cpu and memory
    if node_name in NODES_USAGE_CONSUMPTION_DICT:
        new_node.consumbed_cpu = NODES_USAGE_CONSUMPTION_DICT[node_name].cpu
        new_node.consumbed_memory = NODES_USAGE_CONSUMPTION_DICT[node_name].memory
        new_node.requests_cpu = NODES_USAGE_CONSUMPTION_DICT[node_name].requests_cpu
        new_node.requests_memory = NODES_USAGE_CONSUMPTION_DICT[
            node_name
        ].requests_memory

    # Determine cloud provider
    if new_node.cloud_provider.startswith("aws:"):
        new_node.cloud_provider = CLOUD_PROVIDER_AWS
    elif new_node.cloud_provider.startswith("gce:"):
        new_node.cloud_provider = CLOUD_PROVIDER_GCP
    elif new_node.cloud_provider.startswith("azure:"):
        new_node.cloud_provider = CLOUD_PROVIDER_AZURE
    else:
        node_has_cloud_provider = False
        new_node.cloud_provider = CLOUD_PROVIDER_UNKNOWN

    if node_has_cloud_provider:
        new_node.purchase_option = "on_demand"

    if node_labels != None:
        node_labels = node_labels.items()

        # Get instance-type and region from node labels
        for key, value in node_labels:
            if "instance-type" in key:
                new_node.instance_type = value

            if "region" in key:
                new_node.region = value

            # Set node purchase option based on the cloud provider
            if (
                new_node.cloud_provider == "aws"
                and ("eks.amazonaws.com/capacityType" == key or "node-lifecycle" in key)
                and value.lower() == "spot"
            ):
                new_node.purchase_option = "spot"

            elif (
                new_node.cloud_provider == "gcp"
                and "cloud.google.com/gke-spot" == key
                and value.lower() == "true"
            ):
                new_node.purchase_option = "spot"

            elif (
                new_node.cloud_provider == "azure"
                and "kubernetes.azure.com/scalesetpriority" == key
                and value.lower() == "spot"
            ):
                new_node.purchase_option = "spot"

    if node_has_cloud_provider and (
        not new_node.instance_type
        or not new_node.region
        or not new_node.purchase_option
    ):
        log_info(
            f"WARNING: Skipping node number {index + 1} because it is missing labels"
        )
        continue

    # Add node after it has passed validation
    CLUSTER.nodes.append(new_node)

    # Set node's explicit price using another node that shares the same instance type
    if new_node.instance_type in nodes_sharing_type:
        new_node.explicit_price = nodes_sharing_type[
            new_node.instance_type
        ].explicit_price
        continue

    # If not continued, add the node to shared nodes if it has an instance
    if new_node.instance_type:
        cost_request_message = f"one node of type {new_node.instance_type}"
        nodes_sharing_type[new_node.instance_type] = new_node

    # If the cloud provider is unknown, let the user enter the explicit price of the node
    if not node_has_cloud_provider:
        new_node.explicit_price = float(
            get_input(
                f"Your K8s cluster is hosted by a provider we do not have pricing data for. Please provide the monthly cost for {cost_request_message}:",
                validate_number,
            )
        )


# STEP 7 - Prepare to submit the data
CLUSTER.prepare()
submission = Submission(user_name, user_email, CLUSTER)
log_info("[INFO] Cluster info has been collected successfully \n")

# STEP 8 - Submit the data
submit_cluster(submission)
