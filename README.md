# Control Plane - K8s Cost Analyzer

The K8s Cost Analyzer is designed to help you calculate the cost savings when running workloads on the [Control Plane](https://controlplane.com) platform versus running them on the major cloud providers (AWS, GCP and Azure). By analyzing the resource consumption of your Kubernetes cluster.

Below is an [installation guide](#installation-guide) to help you run the K8s cost analyzer.

The analyzer will require you to enter your name and email. Upon successful execution, a URL will be printed in the terminal and an email containing the result will be sent to you. Visit the URL to view the results of the cost analysis.

## Prerequisites

Before you begin, ensure you have the following:

* Kubernetes CLI (kubectl) installed on the target machine with sufficient privileges to read all objects in the desired cluster.
* Kubernetes Metrics Server installed and healthy in the cluster.
* The desired cluster must **only** be one of the following: Amazon EKS, Azure AKS, or Google GKE.

<h2 id="installation-guide">Installation Guide</h2>

There are two ways in which you can download and run the K8s cost analyzer. You can download and run the Python script directly or you can download the appropriate executable file for your operating system (Windows, macOS or Linux).

### Option 1: Download & Execute the Python script:

1. Clone this repository to your local machine or download the Python script file directly.
2. Open a terminal or a command prompt and navigate to the directory where the Python script is located.
3. Run the script using the following command: `python script_name.py`

### Option 2: Run an executable:

To ensure a seamless experience, we have compiled the Python script using PyInstaller, making it executable on Windows, macOS and Linux. You can easily download the executable file from the [Releases](https://github.com/controlplane-com/k8s-cost-analyzer/releases) section of this repository.

1. Go to the [Releases](https://github.com/controlplane-com/k8s-cost-analyzer/releases) section.
2. Download the appropriate executable file for your operating system (Windows, macOS or Linux).
3. Open your terminal, navigate to the download directory and execute the following commands based on your operating system:

#### For Windows

```pwsh
executable_name.exe
```

#### For macOS & Linux

```bash
chmod +x ./executable_name && ./executable_name
```

## Contribution

We value community engagement and appreciate contributions to enhance this project. If you would like to contribute, please consider the following guidelines:

1. Fork the repository on GitHub to create your own working copy.
2. Create a new branch to isolate your changes.
3. Implement your modifications, following the project's coding style and best practices.
4. Thoroughly test your changes to ensure they function as intended and do not introduce any regressions.
5. Submit a pull request, outlining the purpose and scope of your changes, as well as any necessary documentation updates.
6. Our team will review your contribution, provide feedback if necessary, and work with you to integrate the changes into the main repository.