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
import certifi
import colorama
import threading
import platform
import subprocess
import urllib.request


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


class TopNode:
    def __init__(self, cpu, memory, requests_cpu, requests_memory):
        self.cpu = cpu
        self.memory = memory
        self.requests_cpu = requests_cpu
        self.requests_memory = requests_memory


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


class Cluster:
    def __init__(self):
        self.name = ""
        self.kubernetes_version = ""
        self.total_usage_cpu = 0.0
        self.total_usage_memory = 0.0
        self.components = []
        self.nodes = []

    def prepare(self):
        # Convert CPU from millicores to cores
        self.total_usage_cpu /= 1000
        for component in self.components:
            component.usage_cpu /= 1000
        for node in self.nodes:
            node.capacity_cpu /= 1000


class Submission:
    def __init__(self, user_name, user_email, cluster):
        self.user_name = user_name
        self.user_email = user_email
        self.cluster = cluster


### Constants ###
# General
LOCAL_PORT = 3010
FIND_PORT_MAX_ITERATIONS = 30
DEFAULT_QUERY_TIME_PERIOD = 48
DEFAULT_QUERY_TIME_PERIOD_FORMATTED = f"{DEFAULT_QUERY_TIME_PERIOD}h"
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
    POD_LABELS_COLUMN: 6,
}

TOP_NODES_TABLE_COLUMNS = {
    NODE_NAME_COLUMN: 0,
    NODE_CPU_COLUMN: 1,
    NODE_REQUESTS_CPU_COLUMN: 2,
    NODE_MEMORY_COLUMN: 3,
    NODE_REQUESTS_MEMORY_COLUMN: 4,
}

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


def send_http_post_request(url, json_data):
    """
    Send an http post request

    Parameters:
        Required:
        - url (`str`): The request endpoint.
        - json_data (`str`): The body of the request as json string.

    Returns:
        - response (`str`)
        - status_code (`int`)
    """

    try:
        # Set the Content-Type header
        headers = {"Content-Type": "application/json"}

        # Create a POST request
        request = urllib.request.Request(
            url, data=json_data, headers=headers, method="POST"
        )

        # Send the request and get the response
        with urllib.request.urlopen(request) as response:
            response_data = response.read().decode("utf-8")
            status_code = response.getcode()

        # Return the response data and status code
        return response_data, status_code
    except urllib.error.HTTPError as e:
        # Handle HTTP errors
        error_message = e.read().decode("utf-8")
        error_code = e.code
        return error_message, error_code
    except urllib.error.URLError as e:
        # Handle URL errors
        return str(e), -1


def run_system_command(command, loading_description=""):
    """
    Run a command against the system and return the result.

    Parameters:
        Required:
        - command (`str`): The command to execute against the system.

        Optional:
        - loading_description (`str`): Specify a loading description to
            start loading on command execution.

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
        result, _ = re.match(r"^(\d+)([A-Za-z]+)$", value).groups()

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


def validate_time_period(time_period):
    """
    Validates a time period value (e.g. 24h, 1d) and returns an error message if it is invalid.

    Parameters:
        - time_period (`str`): The time period to validate.

    Returns: The error message as a string.
    """

    pattern = r"^\d+[mhdw]$"
    errorMessage = ""

    if re.match(pattern, time_period) is None:
        errorMessage = "Invalid time period, please try again"

    return errorMessage


def validate_number(str):
    """
    Validates whether the provided string is a number or not.

    Parameters:
        - str (`str`): The string to validate.

    Returns: The error message as a string.
    """

    pattern = r"^[-+]?(\d+(\.\d*)?|\.\d+)([eE][-+]?\d+)?$"
    errorMessage = ""

    if re.match(pattern, str) is None:
        errorMessage = "Invalid input, please enter a valid number"

    return errorMessage


def convert_to_hours(time_period):
    """
    Converts a time period to a number that represents an hour.

    Parameters:
        - time_period (`str`): The time period to convert.

    Returns: The converted hours as an integer.
    """

    unit = time_period[-1]
    value = int(time_period[:-1])

    if unit == "m":
        return value / 60
    elif unit == "h":
        return value
    elif unit == "d":
        return value * 24
    elif unit == "w":
        return value * 24 * 7

    return DEFAULT_QUERY_TIME_PERIOD


def serialize_object(obj):
    """
    Convert class instance to a dictionary

    Parameters:
        - obj (`object`): The object to convert to a dictionary.

    returns: The object as a dictionary.
    """
    return obj.__dict__


### Handle Arguments ###
if len(sys.argv) > 1 and sys.argv[1] == "--version":
    print("v1.0.0")
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
# check_prometheus: bool = get_user_confirmation(
#     "Do you have Prometheus setup on your cluster? (y/n)"
# )

check_prometheus = False
has_prometheus = False
prometheus_namespace = ""

if check_prometheus:
    # Get prometheus namespace
    while True:
        prometheus_namespace = get_input(
            "Insert the namespace for Prometheus: (prometheus)", default="prometheus"
        )

        cmd = f"kubectl get svc -n {prometheus_namespace}"
        cmd_output, cmd_code, cmd_err = run_system_command(
            cmd, f"Searching for the prometheus namespace: '{prometheus_namespace}'"
        )

        if cmd_output.strip() or cmd_code != 0 or cmd_err:
            errorMessage = f"Prometheus server is not found in the specified namespace: '{prometheus_namespace}'"
            if cmd_err:
                errorMessage = try_cmd_error(cmd, cmd_err)

            log_error(errorMessage)

            choice = get_user_confirmation(
                "Would you like to continue without Prometheus or try a different namespace? (continue/retry)",
                "continue",
                "retry",
            )

            if choice:
                prometheus_namespace = ""
                break

# STEP 2 & 3 - Determine the metric collection method and collect data
if prometheus_namespace:
    has_prometheus = True
    time_period = convert_to_hours(
        get_input(
            f"Specify the time period for metric calculation (e.g., 25m/20h/3d/6w): ({DEFAULT_QUERY_TIME_PERIOD_FORMATTED})",
            validate_time_period,
            DEFAULT_QUERY_TIME_PERIOD_FORMATTED,
        )
    )

    # To be continued...

else:
    # Check if 'metrics-server' is functional
    cmd = "kubectl top node"
    top_nodes_output, cmd_code, cmd_err = run_system_command(
        cmd, "Checking if metrics-server is available"
    )

    if cmd_code == 1:
        cmd_err = f"{cmd_err}\nPerhaps your kubeconfig isn’t pointing to a healthy cluster, or your K8s metrics API isn’t available. Please check your K8s cluster, and try again. Email support@controlplane.com and we’ll be happy to help troubleshoot with you"

    if cmd_code != 0:
        exit_script_on_error(try_cmd_error(cmd, cmd_err))

    if len(top_nodes_output.strip().split("\n")) < 2:
        exit_script_on_error(
            f"`{cmd}` command returned an empty list, make sure you have nodes running in your cluster"
        )

    log_info(
        "[INFO] `kubectl top` command will be used to calculate resources consumption\n"
    )

    # STEP 3 - Start collecting metrics
    cmd = "kubectl get pod -A --show-labels"
    get_pods_output, cmd_code, cmd_err = run_system_command(
        cmd, "Collecting pods labels"
    )

    if cmd_code != 0 or cmd_err:
        exit_script_on_error(try_cmd_error(cmd, cmd_err))

    if not get_pods_output or len(get_pods_output.strip().split("\n")) < 2:
        exit_script_on_error(
            f"`{cmd}` command returned an empty list, make sure you have pods running in your cluster"
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

    namespace_to_pod_mapping = {}
    get_pods_lines = get_pods_output.strip().split("\n")
    top_pods_lines = top_pods_output.strip().split("\n")

    # Iterate over pods with labels and map pod name to labels
    for get_pod in get_pods_lines[1:]:
        fields = get_pod.split()

        pod_namespace = fields[GET_PODS_TABLE_COLUMNS[POD_NAMESPACE_COLUMN]]
        pod_name = fields[GET_PODS_TABLE_COLUMNS[POD_NAME_COLUMN]]
        pod_labels = fields[GET_PODS_TABLE_COLUMNS[POD_LABELS_COLUMN]]

        if pod_namespace not in namespace_to_pod_mapping:
            namespace_to_pod_mapping[pod_namespace] = {}

        namespace_to_pod_mapping[pod_namespace][pod_name] = pod_labels

    # Iterate over pods and collect cpu and memory usage
    for top_pod in top_pods_lines[1:]:  # Start from second line and skip header
        fields = top_pod.split()  # Split line into fields

        pod_namespace = fields[TOP_PODS_TABLE_COLUMNS[POD_NAMESPACE_COLUMN]]
        pod_name = fields[TOP_PODS_TABLE_COLUMNS[POD_NAME_COLUMN]]
        pod_container_name = fields[TOP_PODS_TABLE_COLUMNS[POD_CONTAINER_NAME_COLUMN]]
        pod_cpu = extract_value_from_unit(
            fields[TOP_PODS_TABLE_COLUMNS[POD_CPU_COLUMN]]
        )
        pod_memory = extract_value_from_unit(
            fields[TOP_PODS_TABLE_COLUMNS[POD_MEMORY_COLUMN]]
        )
        pod_has_labels = (
            # Check if namespace key exists
            pod_namespace in namespace_to_pod_mapping
            # Check if pod name key exists
            and pod_name in namespace_to_pod_mapping[pod_namespace]
            # Check if labels are not empty
            and namespace_to_pod_mapping[pod_namespace][pod_name]
        )

        if "kube-system" == pod_namespace:
            KUBE_SYSTEM.add_usage(pod_cpu, pod_memory)
        elif "cert-manager" == pod_namespace:
            CERT_MANAGER.add_usage(pod_cpu, pod_memory)
        elif "nats" in pod_namespace:
            NATS.add_usage(pod_cpu, pod_memory)
        elif "knative" in pod_namespace:
            KNATIVE.add_usage(pod_cpu, pod_memory)
        elif "calico" in pod_namespace or "calico" in pod_name:
            CALICO.add_usage(pod_cpu, pod_memory)
        elif "istio" in pod_namespace or "istiod" in pod_name:
            ISTIO.add_usage(pod_cpu, pod_memory)
        elif "istio-proxy" in pod_container_name:
            ISTIO_PROXY.add_usage(pod_cpu, pod_memory)
        elif "linkerd-proxy" in pod_container_name:
            LINKERD.add_usage(pod_cpu, pod_memory)
        elif pod_has_labels:
            pod_labels = namespace_to_pod_mapping[pod_namespace][pod_name]
            if "app.kubernetes.io/name=knative-operator" in pod_labels:
                KNATIVE.add_usage(pod_cpu, pod_memory)
            elif "linkerd.io/control-plane-component" in pod_labels:
                LINKERD.add_usage(pod_cpu, pod_memory)
            elif "linkerd.io/extension=viz" in pod_labels:
                LINKERD_VIZ.add_usage(pod_cpu, pod_memory)
            elif "tigera-operator" in pod_labels:
                CALICO.add_usage(pod_cpu, pod_memory)

        CLUSTER.total_usage_cpu += pod_cpu
        CLUSTER.total_usage_memory += pod_memory

    # Map nodes names to their usage consumption
    top_nodes_dict = {}
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

        top_nodes_dict[node_name] = TopNode(
            node_cpu, node_memory, node_requests_cpu, node_requests_memory
        )


# STEP 4- Get cluster name & kubernetes version
cmd = "kubectl config current-context"
current_context_output, cmd_code, cmd_err = run_system_command(
    cmd, "Getting cluster name"
)

if cmd_code != 0:
    exit_script_on_error(try_cmd_error(cmd, cmd_err))

cmd = "kubectl version --short -o json"
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

# STEP 5 - Process nodes
cmd = "kubectl get nodes -o json"
json_nodes_output, cmd_code, cmd_err = run_system_command(
    cmd, "Collecting info of all nodes in the cluster, please wait"
)

if cmd_code != 0:
    exit_script_on_error(try_cmd_error(cmd, cmd_err))

# Collect nodes info and create new node instances
nodes_sharing_type = {}
nodes_json = json.loads(json_nodes_output)
if "items" not in nodes_json:
    exit_script_on_error("Error: we were unable to find nodes in your cluster")

for index, node_json in enumerate(nodes_json["items"]):
    new_node = Node()
    node_has_cloud_provider = True
    CLUSTER.nodes.append(new_node)

    try:
        node_name = node_json["metadata"]["name"]
        node_capacity_cpu = node_json["status"]["capacity"]["cpu"]
        node_capacity_memory = node_json["status"]["capacity"]["memory"]
        node_allocatable_cpu = node_json["status"]["allocatable"]["cpu"]
        node_allocatable_memory = node_json["status"]["allocatable"]["memory"]
        node_provider_id = node_json["spec"]["providerID"]
        node_labels = node_json["metadata"]["labels"].items()
    except Exception as e:
        log_info(
            f"WARNING: Skipping node number {index + 1} because it is missing expected keys in it's json output"
        )
        continue

    new_node.name = node_name
    new_node.capacity_cpu = extract_value_from_unit(node_capacity_cpu)
    new_node.capacity_memory = extract_value_from_unit(node_capacity_memory)
    new_node.allocatable_cpu = extract_value_from_unit(node_allocatable_cpu) / 1000
    new_node.allocatable_memory = (
        extract_value_from_unit(node_allocatable_memory) / 1024
    )

    # Get node consumbed cpu and memory
    if not has_prometheus:
        new_node.consumbed_cpu = top_nodes_dict[node_name].cpu
        new_node.consumbed_memory = top_nodes_dict[node_name].memory
        new_node.requests_cpu = top_nodes_dict[node_name].requests_cpu
        new_node.requests_memory = top_nodes_dict[node_name].requests_memory

    # Get node cloud provider
    if node_provider_id.startswith("aws:"):
        new_node.cloud_provider = CLOUD_PROVIDER_AWS
    elif node_provider_id.startswith("gce:"):
        new_node.cloud_provider = CLOUD_PROVIDER_GCP
    elif node_provider_id.startswith("azure:"):
        new_node.cloud_provider = CLOUD_PROVIDER_AZURE
    else:
        node_has_cloud_provider = False
        new_node.cloud_provider = CLOUD_PROVIDER_UNKNOWN

    if node_has_cloud_provider:
        new_node.purchase_option = "on_demand"

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

    if new_node.instance_type in nodes_sharing_type:
        new_node.explicit_price = nodes_sharing_type[
            new_node.instance_type
        ].explicit_price
        continue

    cost_request_message = f"this node with the name `{node_name}`"
    if new_node.instance_type:
        cost_request_message = f"one node of type {new_node.instance_type}"
        nodes_sharing_type[new_node.instance_type] = new_node

    if not node_has_cloud_provider:
        new_node.explicit_price = float(
            get_input(
                f"Your K8s cluster is hosted by a provider we do not have pricing data for. Please provide the monthly cost for {cost_request_message}:",
                validate_number,
            )
        )


# STEP 6 - Prepare to submit to the data
CLUSTER.prepare()
submission = Submission(user_name, user_email, CLUSTER)
submission_json = json.dumps(submission, default=serialize_object).encode("utf-8")
log_info("[INFO] Cluster info has been collected successfully \n")

# STEP 7 - Submit the data
LOADING_ANIMATION.start_loading("Submitting the cluster info to the backend")
http_response, http_status = send_http_post_request(ENDPOINT, submission_json)
LOADING_ANIMATION.stop_loading()

if http_status < 200 or http_status > 299:
    exit_script_on_error(http_response)

log_success("The script has executed successfully!")
log_success(f"Here is the link to your result: {json.loads(http_response)}")
